"""Load SEBI's full Recognised Intermediaries lists via the official Excel
export endpoint (the same 'Download' button a browser user clicks):

    https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do?intmId=<id>

Full coverage per category — Name, Registration No., Contact Person, Email,
Telephone — published by SEBI itself. Telephone is the entity's registered
contact number (often a landline), which is why the phone-verdict copy says
"listed as the registered contact of", never "this is their WhatsApp".

Rerunnable; scraped rows carry source='sebi:export' and never touch seeds.
Debarred lists live in SEBI enforcement pages, not this table — still seeded.

Usage: python scripts/scrape_sebi.py
"""
import re
import sys
import tempfile
from pathlib import Path

import httpx
import xlrd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_db, init_db  # noqa: E402

EXPORT = "https://www.sebi.gov.in/sebiweb/other/IntmExportAction.do?intmId={id}"
CATEGORIES = {  # intmId -> kind
    "14": "ra",
    "13": "ria",
    "30": "broker",
    "23": "mf",
}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def parse_export(data: bytes) -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".xls") as f:
        f.write(data)
        f.flush()
        book = xlrd.open_workbook(f.name)
    sheet = book.sheet_by_index(0)
    # locate the header row (contains 'Name' and 'Registration No.')
    header_idx, headers = None, []
    for i in range(min(6, sheet.nrows)):
        vals = [str(c.value).strip() for c in sheet.row(i)]
        if "Name" in vals and any("Registration" in v for v in vals):
            header_idx, headers = i, vals
            break
    if header_idx is None:
        return []
    # headers repeat (registered vs correspondence address) — keep first
    # occurrence for unique fields, ALL occurrences for Telephone
    col = {}
    for j, h in enumerate(headers):
        col.setdefault(h, j)
    name_c = col.get("Name")
    reg_c = next((j for h, j in col.items() if "Registration" in h), None)
    tel_cols = [j for j, h in enumerate(headers) if "Telephone" in h]
    rows = []
    for i in range(header_idx + 1, sheet.nrows):
        vals = [str(c.value).strip() for c in sheet.row(i)]
        name = vals[name_c] if name_c is not None and name_c < len(vals) else ""
        reg = vals[reg_c] if reg_c is not None and reg_c < len(vals) else ""
        tel = next((vals[j] for j in tel_cols if j < len(vals) and vals[j].strip()), "")
        # IN-format for RA/RIA/brokers; MF uses e.g. MF/060/10/01
        if not name or not re.match(r"^(IN[A-Z]\d{9}|MF/\d+/\d+/\d+)$", reg):
            continue
        digits = re.sub(r"\D", "", tel)
        phone = digits[-10:] if len(digits) >= 10 else None
        rows.append({"name": name, "reg_no": reg, "phone": phone})
    return rows


def main():
    init_db()
    total = 0
    with get_db() as db:
        db.execute("DELETE FROM registries WHERE source IN ('scrape:sebi.gov.in','sebi:export')")
        for intm_id, kind in CATEGORIES.items():
            try:
                r = httpx.get(EXPORT.format(id=intm_id), headers=UA,
                              timeout=120, follow_redirects=True)
                r.raise_for_status()
                rows = parse_export(r.content)
            except Exception as e:
                print(f"[{kind}] export failed ({e}) — seeds remain authoritative")
                continue
            for row in rows:
                db.execute(
                    "INSERT INTO registries (kind,name,reg_no,status,phone,source)"
                    " VALUES (?,?,?,?,?,?)",
                    (kind, row["name"], row["reg_no"], "active", row["phone"], "sebi:export"),
                )
            print(f"[{kind}] {len(rows)} rows loaded from official export")
            total += len(rows)
    print(f"done: {total} rows from sebi.gov.in exports (seeds untouched)")


if __name__ == "__main__":
    main()
