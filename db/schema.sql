-- ============================================================================
-- FocusChain CRM — PostgreSQL schema (per-tenant database)
--
-- Multi-tenant model: ONE Postgres server, ONE DATABASE PER ORG
--   (focuschainlabs_db, sn_realtors_db, ...). Each tenant database runs this
--   exact schema. Hard data isolation, but a single low-cost instance.
--
-- Design: a "hot columns + JSONB" hybrid. The fields we filter/search/sort on
-- are real, typed, indexed columns (fast at 10k+ rows). Everything else (the
-- long tail of nested activity, agent context, etc.) lives in `data` JSONB so
-- the flexible document shape the app already uses is preserved.
--
-- Apply with:  psql "$DATABASE_URL" -f db/schema.sql
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fast ILIKE / fuzzy search

-- ── Contacts (the core CRM record) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id              TEXT PRIMARY KEY,           -- app-generated contact id
    company         TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    industry        TEXT NOT NULL DEFAULT '',
    owner           TEXT NOT NULL DEFAULT '',
    client          TEXT NOT NULL DEFAULT '',
    value           TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'new',     -- new/contacted/qualified/proposal/won/lost
    deal_status     TEXT NOT NULL DEFAULT 'open',    -- open/won/lost
    source          TEXT NOT NULL DEFAULT 'other',
    next_follow_up  DATE,
    data            JSONB NOT NULL DEFAULT '{}',     -- comments, email_events, contact_people, invoices, agent ctx
    fingerprint     TEXT,                            -- dedupe key (company+email/phone)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes that make 10k+ records snappy ----------------------------------------
CREATE INDEX IF NOT EXISTS idx_contacts_status      ON contacts (status);
CREATE INDEX IF NOT EXISTS idx_contacts_deal_status ON contacts (deal_status);
CREATE INDEX IF NOT EXISTS idx_contacts_source      ON contacts (source);
CREATE INDEX IF NOT EXISTS idx_contacts_follow_up   ON contacts (next_follow_up);
CREATE INDEX IF NOT EXISTS idx_contacts_updated     ON contacts (updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_fingerprint
    ON contacts (fingerprint) WHERE fingerprint IS NOT NULL AND fingerprint <> '';

-- Trigram indexes for fast partial-text search across the fields users type into
CREATE INDEX IF NOT EXISTS idx_contacts_company_trgm ON contacts USING gin (company gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_name_trgm    ON contacts USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_email_trgm   ON contacts USING gin (email gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_phone_trgm   ON contacts USING gin (phone gin_trgm_ops);
-- JSONB GIN for searching inside notes/activity when needed
CREATE INDEX IF NOT EXISTS idx_contacts_data_gin     ON contacts USING gin (data jsonb_path_ops);

-- ── Invoices (Finance Agent) — promoted to first-class rows for reporting ─────
-- Mirrors what's also kept in contacts.data so cashflow queries can aggregate
-- in SQL instead of scanning every contact in Python.
CREATE TABLE IF NOT EXISTS invoices (
    id              TEXT PRIMARY KEY,
    number          TEXT NOT NULL,
    contact_id      TEXT REFERENCES contacts(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'draft',   -- draft/sent/paid/cancelled (overdue is computed)
    currency        TEXT NOT NULL DEFAULT 'INR',
    subtotal        NUMERIC(14,2) NOT NULL DEFAULT 0,
    tax             NUMERIC(14,2) NOT NULL DEFAULT 0,
    total           NUMERIC(14,2) NOT NULL DEFAULT 0,
    issue_date      DATE,
    due_date        DATE,
    data            JSONB NOT NULL DEFAULT '{}',      -- line items, dunning log, payment terms
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_invoices_contact ON invoices (contact_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status  ON invoices (status);
CREATE INDEX IF NOT EXISTS idx_invoices_due     ON invoices (due_date);

-- ── Lightweight metadata (schema version, last sync, custom statuses) ─────────
CREATE TABLE IF NOT EXISTS crm_meta (
    key     TEXT PRIMARY KEY,
    value   JSONB NOT NULL DEFAULT '{}'
);
INSERT INTO crm_meta (key, value)
VALUES ('schema', '{"version": 1}')
ON CONFLICT (key) DO NOTHING;

-- Keep updated_at fresh on every write ---------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contacts_touch ON contacts;
CREATE TRIGGER trg_contacts_touch BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_invoices_touch ON invoices;
CREATE TRIGGER trg_invoices_touch BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
