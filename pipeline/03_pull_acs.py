"""
Pull ACS 5-year housing characteristics for NJ ZCTAs and write them to
nj_lmp.db so gen_ui_json.py can compute a per-ZIP consumption index for
modeled residential bills.

Tables pulled (ACS 5-year 2023, latest available as of 2026):
  B25024 — Units in Structure (housing-mix lever)
  B25018 — Median number of rooms per unit (home-size lever)

Why these two:
  - EIA-861M gives one residential bill per utility (same value for every
    ZIP in a service territory). Real per-ZIP consumption varies mostly
    with housing mix (apartments use far less than detached SFH) and home
    size. ACS B25024 + B25018 capture both at the ZCTA level.

Auth:
  Requires a free Census API key. Get one at
      https://api.census.gov/data/key_signup.html
  Then either:
      $env:CENSUS_API_KEY = "your-key-here"   # PowerShell
      export CENSUS_API_KEY=your-key-here     # bash
  or drop it into a .env file in this directory as
      CENSUS_API_KEY=your-key-here

Run:
    python pull_acs.py
"""

import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import requests

# Project root = parent of this pipeline/ folder.
ROOT      = Path(__file__).resolve().parent.parent
DB_FILE   = str(ROOT / "data" / "nj_lmp.db")
ACS_YEAR  = 2023                    # ACS 5-year 2019-2023
BASE_URL  = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"

B25024_VARS = {
    "B25024_001E": "total_units",
    "B25024_002E": "u_1_detached",
    "B25024_003E": "u_1_attached",
    "B25024_004E": "u_2",
    "B25024_005E": "u_3_4",
    "B25024_006E": "u_5_9",
    "B25024_007E": "u_10_19",
    "B25024_008E": "u_20_49",
    "B25024_009E": "u_50_plus",
    "B25024_010E": "u_mobile",
    "B25024_011E": "u_other",
}
B25018_VARS = {"B25018_001E": "median_rooms"}

# B25040 — House Heating Fuel. Electric vs gas heat is the single biggest swing
# in residential kWh (an electric-heat home uses 2-3x an identical gas one), so
# the electricity share is a high-value feature for the consumption model.
B25040_VARS = {
    "B25040_001E": "heat_total",
    "B25040_002E": "heat_utility_gas",
    "B25040_003E": "heat_lp_gas",
    "B25040_004E": "heat_electricity",
    "B25040_005E": "heat_fuel_oil",
}

# B19013 — Median household income. Wealth drives square footage, central AC,
# pools, EVs — all consumption.
B19013_VARS = {"B19013_001E": "median_income"}

ALL_VARS = {**B25024_VARS, **B25018_VARS, **B25040_VARS, **B19013_VARS}


def load_dotenv(path: str = str(ROOT / ".env")) -> None:
    """Minimal .env loader so we don't add python-dotenv as a dep."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def nj_zips_from_db(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT zip FROM zips").fetchall()
    return {str(r[0]).zfill(5) for r in rows}


def fetch_acs(api_key: str) -> pd.DataFrame:
    """One batched API call for every US ZCTA. Filtered to NJ later."""
    var_str = ",".join(ALL_VARS.keys())
    params = {
        "get":  var_str,
        "for":  "zip code tabulation area:*",
        "key":  api_key,
    }
    print(f"Fetching ACS {ACS_YEAR} 5-year B25024 + B25018 for all US ZCTAs...")
    r = requests.get(BASE_URL, params=params, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Census API returned {r.status_code}: {r.text[:300]}")

    # Census returns HTTP 200 + HTML for auth failures instead of a proper 401.
    if r.text.lstrip().startswith("<"):
        if "Invalid Key" in r.text:
            raise RuntimeError(
                "Census API rejected CENSUS_API_KEY as invalid. "
                "If you just signed up, check your email for an activation link "
                "from census.gov — the key only works after you click it."
            )
        raise RuntimeError(f"Census API returned HTML instead of JSON: {r.text[:300]}")

    rows = r.json()
    header, data = rows[0], rows[1:]
    df = pd.DataFrame(data, columns=header)
    df = df.rename(columns={**ALL_VARS, "zip code tabulation area": "zip"})
    df["zip"] = df["zip"].astype(str).str.zfill(5)

    for col in ALL_VARS.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # Census uses large negative sentinels (-666666666, -999999999, ...)
        # to flag "estimate not displayed / not applicable / too few cases".
        # Counts and median-rooms are always >= 0 in reality, so nuke them.
        df.loc[df[col] < 0, col] = pd.NA

    print(f"  pulled {len(df)} ZCTAs nationally")
    return df


def create_table(conn: sqlite3.Connection) -> None:
    # Drop and recreate so newly added ACS variables become columns. This is a
    # full-refresh pull from the API, so nothing is lost.
    cols = ",\n            ".join(f"{name} REAL" for name in ALL_VARS.values())
    conn.executescript(f"""
        DROP TABLE IF EXISTS acs_zcta;
        CREATE TABLE acs_zcta (
            zip TEXT PRIMARY KEY,
            {cols},
            acs_year INTEGER
        );
    """)
    conn.commit()


def upsert(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    cols = ["zip"] + list(ALL_VARS.values()) + ["acs_year"]
    placeholders = ",".join(f":{c}" for c in cols)
    updates = ",".join(f"{c} = excluded.{c}" for c in cols if c != "zip")
    df = df.copy()
    df["acs_year"] = ACS_YEAR
    rows = df[cols].to_dict("records")
    conn.executemany(f"""
        INSERT INTO acs_zcta ({",".join(cols)}) VALUES ({placeholders})
        ON CONFLICT(zip) DO UPDATE SET {updates}
    """, rows)
    conn.commit()
    return len(rows)


def main():
    load_dotenv()
    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        sys.stderr.write(
            "ERROR: CENSUS_API_KEY not set.\n"
            "Get a free key at https://api.census.gov/data/key_signup.html\n"
            "then `export CENSUS_API_KEY=...` (or add it to .env).\n"
        )
        sys.exit(1)

    if not os.path.exists(DB_FILE):
        sys.stderr.write(f"ERROR: {DB_FILE} not found. Run init_db.py first.\n")
        sys.exit(1)

    conn = sqlite3.connect(DB_FILE)
    try:
        nj_zips = nj_zips_from_db(conn)
        print(f"NJ ZIPs from zips table: {len(nj_zips)}")

        all_df = fetch_acs(api_key)
        nj_df  = all_df[all_df["zip"].isin(nj_zips)].copy()
        print(f"  filtered to {len(nj_df)} NJ ZCTAs")

        # Drop ZCTAs with no housing data (PO-box-only ZIPs etc).
        nj_df = nj_df[nj_df["total_units"] > 0].copy()
        print(f"  {len(nj_df)} NJ ZCTAs have non-zero housing units")

        create_table(conn)
        n = upsert(conn, nj_df)
        print(f"\nacs_zcta: upserted {n} rows for ACS {ACS_YEAR} 5-year")

        cur = conn.execute(
            "SELECT COUNT(*), AVG(median_rooms), AVG(u_1_detached / NULLIF(total_units,0)) "
            "FROM acs_zcta"
        )
        n, avg_rooms, avg_sfh_share = cur.fetchone()
        print(f"  {n} rows · avg median rooms {avg_rooms:.2f} "
              f"· avg detached-SFH share {avg_sfh_share*100:.1f}%")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
