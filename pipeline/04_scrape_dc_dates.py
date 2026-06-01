"""
Enrich ui/data_centers.json with approval/application years scraped from
interconnection.fyi project pages.

Adds fields:
  application_year : int | None
  approval_year    : int | None
  start_year       : int | None   # approval_year if present, else application_year
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

# Project root = parent of this pipeline/ folder.
ROOT    = Path(__file__).resolve().parent.parent
DC_PATH = ROOT / "ui" / "data_centers.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (research scraper)"}

ROW_RE = re.compile(
    r"<td[^>]*>\s*(Application Date|Approval Date)\s*</td>\s*"
    r"<td[^>]*>\s*<p[^>]*>\s*(\d{4})\s*</p>",
    re.IGNORECASE,
)


def scrape(url: str) -> dict:
    try:
        r = requests.get(url, timeout=20, headers=HEADERS)
        r.raise_for_status()
    except Exception as e:
        print(f"  ! fetch failed: {e}")
        return {}
    out = {}
    for label, year in ROW_RE.findall(r.text):
        key = "application_year" if label.lower().startswith("application") else "approval_year"
        out[key] = int(year)
    return out


def main() -> int:
    records = json.loads(DC_PATH.read_text(encoding="utf-8"))
    print(f"loaded {len(records)} data centers")

    for i, rec in enumerate(records, 1):
        name = rec.get("name", "?")
        url = rec.get("url") or ""
        print(f"[{i:2}/{len(records)}] {name}")
        if not url:
            rec.setdefault("application_year", None)
            rec.setdefault("approval_year", None)
            rec.setdefault("start_year", None)
            continue

        dates = scrape(url)
        rec["application_year"] = dates.get("application_year")
        rec["approval_year"] = dates.get("approval_year")
        rec["start_year"] = rec["approval_year"] or rec["application_year"]
        print(f"    app={rec['application_year']} approval={rec['approval_year']} start={rec['start_year']}")
        time.sleep(0.4)

    DC_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
    found = sum(1 for r in records if r.get("start_year"))
    print(f"done — populated start_year for {found}/{len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
