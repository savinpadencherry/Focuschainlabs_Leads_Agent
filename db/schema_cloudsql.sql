CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Multi-tenancy: shared tables, one row per tenant in `organizations`, every
-- tenant-owned row elsewhere carries organization_id. All existing data
-- before this migration belongs to the seeded 'default' org.
CREATE TABLE IF NOT EXISTS organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO organizations (id, name) VALUES ('default', 'Default')
    ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS contacts (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL DEFAULT '',
    company             TEXT NOT NULL DEFAULT '',
    industry            TEXT NOT NULL DEFAULT '',
    phone               TEXT NOT NULL DEFAULT '',
    email               TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'new',
    deal_status         TEXT NOT NULL DEFAULT 'open',
    value               TEXT NOT NULL DEFAULT '',
    owner               TEXT NOT NULL DEFAULT '',
    source              TEXT NOT NULL DEFAULT 'other',
    sentiment           TEXT NOT NULL DEFAULT '',
    next_follow_up      DATE,
    notes               TEXT NOT NULL DEFAULT '',
    tags                TEXT[] DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    wa_phone_number_id  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS interactions (
    id           TEXT PRIMARY KEY,
    contact_id   TEXT REFERENCES contacts(id) ON DELETE CASCADE,
    author       TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    kind         TEXT NOT NULL DEFAULT 'comment',
    subject      TEXT NOT NULL DEFAULT '',
    meeting_link TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- WhatsApp message/status tracking. Added after the initial release — these
-- ALTERs are idempotent so this file can be re-applied to the live instance.
-- direction: 'inbound' | 'outbound'. message_id: Meta wamid, used both to
-- de-duplicate retried webhook deliveries and to match later status receipts
-- (sent/delivered/read/failed) back to the row that recorded the send.
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS direction      TEXT NOT NULL DEFAULT '';
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS message_id     TEXT NOT NULL DEFAULT '';
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS status         TEXT NOT NULL DEFAULT '';
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS campaign_id    TEXT NOT NULL DEFAULT '';
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS template_name  TEXT NOT NULL DEFAULT '';
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS error          TEXT NOT NULL DEFAULT '';
-- processed_at: when the daily AI batch (scripts/process_inbound_daily.py) has
-- folded this inbound message into its contact's CRM record. NULL = still
-- pending. Realtime-handled messages are stamped at insert so the batch never
-- redoes them; this makes the batch idempotent and cheap to re-run.
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS processed_at   TIMESTAMPTZ;

-- Multi-number WhatsApp coexistence:
-- Each agent connects their WhatsApp Business number via Embedded Signup.
-- Their phone_number_id + access_token gets stored here.
-- contacts.wa_phone_number_id references whatsapp_accounts.phone_number_id
-- so we always know which agent number a lead belongs to.
CREATE TABLE IF NOT EXISTS whatsapp_accounts (
    id                TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    phone_number_id   TEXT UNIQUE NOT NULL,
    display_name      TEXT NOT NULL DEFAULT '',
    phone_number      TEXT NOT NULL DEFAULT '',
    waba_id           TEXT NOT NULL DEFAULT '',
    access_token      TEXT NOT NULL DEFAULT '',
    agent_name        TEXT NOT NULL DEFAULT '',
    connected_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    active            BOOLEAN NOT NULL DEFAULT true
);

-- organization_id backfill: existing rows get 'default' via the column
-- DEFAULT, then DROP DEFAULT so every future insert must name a tenant
-- explicitly — a missing organization_id fails loudly (NOT NULL) instead of
-- silently landing in the wrong tenant's data.
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE contacts ALTER COLUMN organization_id DROP DEFAULT;
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE interactions ALTER COLUMN organization_id DROP DEFAULT;
ALTER TABLE whatsapp_accounts ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE whatsapp_accounts ALTER COLUMN organization_id DROP DEFAULT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contacts_org') THEN
        ALTER TABLE contacts ADD CONSTRAINT fk_contacts_org
            FOREIGN KEY (organization_id) REFERENCES organizations(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_interactions_org') THEN
        ALTER TABLE interactions ADD CONSTRAINT fk_interactions_org
            FOREIGN KEY (organization_id) REFERENCES organizations(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_whatsapp_accounts_org') THEN
        ALTER TABLE whatsapp_accounts ADD CONSTRAINT fk_whatsapp_accounts_org
            FOREIGN KEY (organization_id) REFERENCES organizations(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_contacts_org        ON contacts(organization_id);
CREATE INDEX IF NOT EXISTS idx_interactions_org    ON interactions(organization_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_accounts_org ON whatsapp_accounts(organization_id);
CREATE INDEX IF NOT EXISTS idx_contacts_status     ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_contacts_updated    ON contacts(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_phone      ON contacts(phone);
CREATE INDEX IF NOT EXISTS idx_contacts_wa_pid     ON contacts(wa_phone_number_id);
CREATE INDEX IF NOT EXISTS idx_interactions_cid    ON interactions(contact_id);
-- Fast lookup of the daily batch's work queue: unprocessed inbound messages.
CREATE INDEX IF NOT EXISTS idx_interactions_unprocessed
    ON interactions(organization_id, contact_id)
    WHERE processed_at IS NULL AND direction = 'inbound';
CREATE UNIQUE INDEX IF NOT EXISTS idx_interactions_message_id
    ON interactions(message_id) WHERE message_id <> '';

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contacts_touch ON contacts;
CREATE TRIGGER trg_contacts_touch BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
