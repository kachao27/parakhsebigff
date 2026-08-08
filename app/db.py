"""SQLite store. Schema per PRD §7: registries, blacklist, fingerprints,
sightings, campaigns.

DPDP note: no message content is ever stored. Sightings hold only the
artifact hash, type, verdict and rule/match id. The sender wa_id is kept
solely to deliver advisory push-backs (FR7) and can be purged.
"""
import sqlite3
import time
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS registries (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,          -- ra | ria | broker | mf | debarred
    name TEXT NOT NULL,
    reg_no TEXT,
    entity TEXT,                 -- individual | non-individual
    valid_till TEXT,
    status TEXT NOT NULL,        -- active | debarred | expired
    phone TEXT,                  -- seed-only mapping; registries do not index phones
    source TEXT                  -- scrape:<url> | seed
);
CREATE INDEX IF NOT EXISTS idx_reg_no ON registries(reg_no);
CREATE INDEX IF NOT EXISTS idx_reg_phone ON registries(phone);

CREATE TABLE IF NOT EXISTS blacklist (
    kind TEXT NOT NULL,          -- phone | upi | url
    value TEXT NOT NULL,
    source TEXT,
    ref TEXT,                    -- advisory reference
    PRIMARY KEY (kind, value)
);

CREATE TABLE IF NOT EXISTS fingerprints (
    id INTEGER PRIMARY KEY,
    hash TEXT NOT NULL,          -- 16-hex pHash (64 bit)
    kind TEXT NOT NULL,          -- video | image | audio
    label TEXT NOT NULL,
    advisory_ref TEXT,
    first_seen REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fp_kind ON fingerprints(kind);

CREATE TABLE IF NOT EXISTS sightings (
    id INTEGER PRIMARY KEY,
    artifact_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    verdict TEXT NOT NULL,       -- red | green | amber
    ref_id TEXT,                 -- rule id / reg_no / fingerprint id
    ts REAL NOT NULL,
    channel TEXT NOT NULL,       -- whatsapp | web
    sender TEXT                  -- wa_id, advisory delivery only
);
CREATE INDEX IF NOT EXISTS idx_sight_hash ON sightings(artifact_hash);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY,
    hash TEXT NOT NULL UNIQUE,
    count INTEGER NOT NULL,
    first_seen REAL NOT NULL,
    status TEXT NOT NULL,        -- active | advised
    advisory_text TEXT,
    sample_verdict TEXT,
    kind TEXT,
    intel TEXT                   -- cached AI intelligence brief (JSON)
);
"""


def _migrate(db):
    """Add columns introduced after first deploy (SQLite has no IF NOT EXISTS
    for columns; ignore the error if already present)."""
    for col, decl in [("intel", "TEXT")]:
        try:
            db.execute(f"ALTER TABLE campaigns ADD COLUMN {col} {decl}")
        except Exception:
            pass


@contextmanager
def get_db():
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)
        _migrate(db)


def record_sighting(artifact_hash, kind, verdict, ref_id, channel, sender=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO sightings (artifact_hash, kind, verdict, ref_id, ts, channel, sender)"
            " VALUES (?,?,?,?,?,?,?)",
            (artifact_hash, kind, verdict, ref_id, time.time(), channel, sender),
        )
        _update_campaign(db, artifact_hash, kind, verdict, ref_id)


def _update_campaign(db, artifact_hash, kind, verdict, ref_id):
    """FR7: same-hash red/amber sightings >= threshold within window -> campaign."""
    if verdict == "green":
        return
    since = time.time() - settings.campaign_window_hours * 3600
    row = db.execute(
        "SELECT COUNT(*) c, MIN(ts) f FROM sightings WHERE artifact_hash=? AND ts>?",
        (artifact_hash, since),
    ).fetchone()
    if row["c"] >= settings.campaign_threshold:
        db.execute(
            "INSERT INTO campaigns (hash, count, first_seen, status, sample_verdict, kind)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(hash) DO UPDATE SET count=excluded.count",
            (artifact_hash, row["c"], row["f"], "active", f"{verdict}:{ref_id or ''}", kind),
        )


def senders_of(artifact_hash):
    with get_db() as db:
        rows = db.execute(
            "SELECT DISTINCT sender FROM sightings WHERE artifact_hash=? AND sender IS NOT NULL",
            (artifact_hash,),
        ).fetchall()
    return [r["sender"] for r in rows]
