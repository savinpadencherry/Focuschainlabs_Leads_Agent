CREATE EXTENSION IF NOT EXISTS pg_trgm;

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

CREATE INDEX IF NOT EXISTS idx_contacts_status     ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_contacts_updated    ON contacts(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_phone      ON contacts(phone);
CREATE INDEX IF NOT EXISTS idx_contacts_wa_pid     ON contacts(wa_phone_number_id);
CREATE INDEX IF NOT EXISTS idx_interactions_cid    ON interactions(contact_id);

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contacts_touch ON contacts;
CREATE TRIGGER trg_contacts_touch BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
