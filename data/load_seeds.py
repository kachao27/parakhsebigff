"""Load seed CSVs into the SQLite store. Rerunnable (wipes + reloads seeds).

Rows with source starting 'seed:' are seed data (synthetic or public),
stated openly in the README. scripts/scrape_sebi.py replaces synthetic rows
with real registry data where the scrape succeeds.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_db, init_db  # noqa: E402

SEEDS = Path(__file__).parent / "seeds"


def load():
    init_db()
    with get_db() as db:
        db.execute("DELETE FROM registries WHERE source LIKE 'seed:%' OR source LIKE 'advisory:%'")
        for name in ("registries.csv", "advisories.csv"):
            with open(SEEDS / name) as f:
                for row in csv.DictReader(f):
                    db.execute(
                        "INSERT INTO registries (kind,name,reg_no,entity,valid_till,status,phone,source)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (row["kind"], row["name"], row["reg_no"] or None, row["entity"] or None,
                         row["valid_till"] or None, row["status"], row["phone"] or None, row["source"]),
                    )
        db.execute("DELETE FROM blacklist WHERE source LIKE 'seed:%'")
        with open(SEEDS / "blacklist.csv") as f:
            for row in csv.DictReader(f):
                db.execute(
                    "INSERT OR REPLACE INTO blacklist (kind,value,source,ref) VALUES (?,?,?,?)",
                    (row["kind"], row["value"], row["source"], row["ref"]),
                )
    print("seeds loaded")


if __name__ == "__main__":
    load()
