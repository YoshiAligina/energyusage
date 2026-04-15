"""
Initialize SQLite database and migrate existing CSV data.

Schema:
  zips       — static zip metadata (one row per zip)
  lmp_daily  — daily LMP at the node level (one row per node+date)

Run once:
    python init_db.py
"""

import sqlite3
import pandas as pd
import os

DB_FILE  = "nj_lmp.db"
CSV_FILE = "nj_zip_lmp_jan1_2020_2025.csv"  # one-time migration source; deleted after first run
YEARS    = range(2020, 2026)


def create_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS zips (
            zip           TEXT PRIMARY KEY,
            zip_lat       REAL,
            zip_lon       REAL,
            nearest_node  TEXT,
            node_zone     TEXT,
            dist_miles    REAL,
            coord_quality TEXT
        );

        CREATE TABLE IF NOT EXISTS lmp_daily (
            node  TEXT    NOT NULL,
            date  TEXT    NOT NULL,   -- 'YYYY-MM-DD'
            lmp   REAL,
            PRIMARY KEY (node, date)
        );

        CREATE INDEX IF NOT EXISTS idx_lmp_daily_node ON lmp_daily (node);
        CREATE INDEX IF NOT EXISTS idx_lmp_daily_date ON lmp_daily (date);
        CREATE INDEX IF NOT EXISTS idx_zips_node      ON zips (nearest_node);
    """)
    conn.commit()


def migrate_csv(conn: sqlite3.Connection, csv_path: str):
    df = pd.read_csv(csv_path, dtype={"zip": str})
    df["zip"] = df["zip"].str.zfill(5)

    # ── zips table ──────────────────────────────────────────────────────────
    zip_cols = ["zip", "zip_lat", "zip_lon", "nearest_node",
                "node_zone", "dist_miles", "coord_quality"]
    zips_df = df[zip_cols].copy()
    zips_df.to_sql("zips", conn, if_exists="replace", index=False)
    print(f"  Inserted {len(zips_df)} rows -> zips")

    # ── lmp_daily table ─────────────────────────────────────────────────────
    # Current data is Jan 1 snapshots; store as YYYY-01-01 dates.
    # Deduplicate: if multiple zips share a node, the LMP value is identical,
    # so we keep one row per (node, date).
    lmp_rows = []
    for year in YEARS:
        col = f"lmp_{year}"
        if col not in df.columns:
            continue
        date_str = f"{year}-01-01"
        chunk = (df[["nearest_node", col]]
                   .dropna(subset=[col])
                   .drop_duplicates("nearest_node")
                   .rename(columns={"nearest_node": "node", col: "lmp"}))
        chunk["date"] = date_str
        lmp_rows.append(chunk[["node", "date", "lmp"]])

    lmp_df = pd.concat(lmp_rows, ignore_index=True)
    lmp_df.to_sql("lmp_daily", conn, if_exists="replace", index=False)
    print(f"  Inserted {len(lmp_df)} rows -> lmp_daily "
          f"({lmp_df['node'].nunique()} unique nodes × {len(YEARS)} dates)")


if __name__ == "__main__":
    if os.path.exists(DB_FILE):
        print(f"'{DB_FILE}' already exists — dropping and recreating.")
        os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    try:
        print("Creating tables...")
        create_tables(conn)
        print(f"Migrating '{CSV_FILE}'...")
        migrate_csv(conn, CSV_FILE)
        print(f"\nDone. Database: {DB_FILE}")

        # Quick sanity check
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM zips")
        print(f"  zips rows:      {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*) FROM lmp_daily")
        print(f"  lmp_daily rows: {cur.fetchone()[0]}")
    finally:
        conn.close()
