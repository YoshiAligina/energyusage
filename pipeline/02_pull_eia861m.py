"""
Pull EIA-861M (monthly retail sales/revenue) for NJ investor-owned utilities
and store per-utility monthly rate + bill in nj_lmp.db.

Source: https://www.eia.gov/electricity/data/eia861m/
Downloads one XLSX per year, filters for NJ IOUs, computes:
  - rate_cents_per_kwh = revenue / sales * 100
  - bill_dollars       = revenue / customer_count
  - kwh_per_customer   = sales / customer_count
Writes to table `utility_monthly`.

Run:
    python pull_eia861m.py
"""

import io
import os
import sqlite3
from pathlib import Path

import pandas as pd
import requests

# Project root = parent of this pipeline/ folder.
ROOT     = Path(__file__).resolve().parent.parent
DB_FILE  = str(ROOT / "data" / "nj_lmp.db")
DATA_DIR = str(ROOT / "data" / "raw")           # cached source XLSX live here
YEARS    = range(2020, 2027)

# NJ investor-owned distribution utilities (the ones that send bills).
NJ_IOUS = {
    963:   "Atlantic City Electric",
    9726:  "JCP&L",
    15477: "PSE&G",
    16213: "Rockland Electric",
}

CURRENT_YEAR_URL = "https://www.eia.gov/electricity/data/eia861m/xls/sales_ult_cust_{year}.xlsx"
ARCHIVE_URL      = "https://www.eia.gov/electricity/data/eia861m/archive/xls/sales_ult_cust_{year}.xlsx"
# 2020 has a different file name in the archive.
SPECIAL_URLS = {
    2020: "https://www.eia.gov/electricity/data/eia861m/archive/xls/retail_sales_2020.xlsx",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; nj-energy-explorer/1.0)"}


def url_for(year: int) -> str:
    if year in SPECIAL_URLS:
        return SPECIAL_URLS[year]
    # The "current year" file lives at a different URL from archived years.
    # Probe archive first; fall back to current-year path if archive 404s.
    return ARCHIVE_URL.format(year=year)


def download(year: int) -> str:
    """Download the XLSX for `year` into data/, return local path.
    Tries archive URL first, then current-year URL."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"eia861m_{year}.xlsx")
    if os.path.exists(path) and os.path.getsize(path) > 100_000:
        return path  # cached

    candidates = [url_for(year)]
    if year not in SPECIAL_URLS:
        candidates.append(CURRENT_YEAR_URL.format(year=year))

    for url in candidates:
        r = requests.get(url, headers=HEADERS, timeout=60)
        if r.status_code == 200 and r.content.startswith(b"PK"):  # xlsx magic
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    raise RuntimeError(f"Could not download EIA-861M for {year} (tried {candidates})")


def parse_year(path: str, year: int) -> pd.DataFrame:
    """Return per-month residential rows for the 4 NJ IOUs."""
    df = pd.read_excel(path, sheet_name="Sales Ultimate Cust. -States", header=2)
    df = df[(df["State"] == "NJ") & (df["Utility Number"].isin(NJ_IOUS))].copy()
    # Residential block starts at column index 7 (Thousands Dollars, MWh, Count).
    df = df.rename(columns={
        "Utility Number":    "utility_id",
        "Thousands Dollars": "res_rev_thousand",
        "Megawatthours":     "res_sales_mwh",
        "Count":             "res_customers",
    })
    df["utility_id"]     = df["utility_id"].astype(int)
    df["year"]           = df["Year"].astype(int)
    df["month"]          = df["Month"].astype(int)
    df["res_rev_dollar"] = df["res_rev_thousand"] * 1000.0
    df["res_sales_kwh"]  = df["res_sales_mwh"] * 1000.0

    # Skip rows with zero or missing customers/sales (data not yet reported).
    df = df[(df["res_customers"] > 0) & (df["res_sales_kwh"] > 0)]

    df["rate_cents_per_kwh"] = (df["res_rev_dollar"] / df["res_sales_kwh"]) * 100.0
    df["bill_dollars"]       = df["res_rev_dollar"] / df["res_customers"]
    df["kwh_per_customer"]   = df["res_sales_kwh"] / df["res_customers"]

    return df[["year", "month", "utility_id",
               "res_customers", "res_sales_mwh", "res_rev_thousand",
               "rate_cents_per_kwh", "bill_dollars", "kwh_per_customer"]]


def create_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS utility_monthly (
            utility_id         INTEGER NOT NULL,
            year               INTEGER NOT NULL,
            month              INTEGER NOT NULL,
            res_customers      INTEGER,
            res_sales_mwh      REAL,
            res_rev_thousand   REAL,
            rate_cents_per_kwh REAL,
            bill_dollars       REAL,
            kwh_per_customer   REAL,
            PRIMARY KEY (utility_id, year, month)
        );
        CREATE INDEX IF NOT EXISTS idx_utility_monthly_year
            ON utility_monthly (year, month);
    """)
    conn.commit()


def upsert(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    rows = df.to_dict("records")
    conn.executemany("""
        INSERT INTO utility_monthly (
            utility_id, year, month,
            res_customers, res_sales_mwh, res_rev_thousand,
            rate_cents_per_kwh, bill_dollars, kwh_per_customer
        ) VALUES (
            :utility_id, :year, :month,
            :res_customers, :res_sales_mwh, :res_rev_thousand,
            :rate_cents_per_kwh, :bill_dollars, :kwh_per_customer
        )
        ON CONFLICT(utility_id, year, month) DO UPDATE SET
            res_customers      = excluded.res_customers,
            res_sales_mwh      = excluded.res_sales_mwh,
            res_rev_thousand   = excluded.res_rev_thousand,
            rate_cents_per_kwh = excluded.rate_cents_per_kwh,
            bill_dollars       = excluded.bill_dollars,
            kwh_per_customer   = excluded.kwh_per_customer
    """, rows)
    conn.commit()
    return len(rows)


def main():
    conn = sqlite3.connect(DB_FILE)
    try:
        create_table(conn)
        total = 0
        for year in YEARS:
            try:
                path = download(year)
            except Exception as e:
                print(f"  {year}: SKIP — {e}")
                continue
            df = parse_year(path, year)
            n = upsert(conn, df)
            months = sorted(df["month"].unique().tolist())
            total += n
            print(f"  {year}: {n} rows · months {months}")

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(year||'-'||printf('%02d', month)), "
                    "MAX(year||'-'||printf('%02d', month)) FROM utility_monthly")
        count, first, last = cur.fetchone()
        print(f"\nutility_monthly: {count} rows · {first} to {last}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
