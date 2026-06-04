"""
Does proximity to a data center raise wholesale electricity prices?

This is the core research question. Retail rates are set uniformly across a
utility's whole service territory, so a *local* data-center effect cannot show up
in residential bills below the utility level (see 05/06). Wholesale day-ahead
LMP, however, is locational by construction: if a data center adds load and
congests the grid, nearby PJM nodes carry a higher price. So LMP is the right
instrument to look for a local effect.

Method
------
1. Locate each PJM node as the centroid of the ZIP centroids that map to it
   (node coordinates aren't stored; this is the available proxy).
2. Isolate the LOCATIONAL PREMIUM = node LMP - statewide mean LMP on the same
   date. The raw LMP is dominated by market-wide energy swings (NJ monthly mean
   ran ~$18 -> ~$87 -> ~$46 over 2020-2026); subtracting the statewide mean per
   date strips that common trend and leaves the part of a node's price that is
   specific to its location (congestion).
3. Relate each node's premium to its distance to the nearest data center:
   - cross-sectional correlation per year (pooled and within utility zone),
   - growth of the premium 2020 -> 2026,
   - an event-time check: for data centers that came online during the panel,
     does the premium at nearby nodes rise around the online year relative to
     far nodes?

Caveats (reported, not hidden): proximity is endogenous -- data centers site in
existing load pockets that already have higher LMP -- so a negative
distance-premium correlation is partly siting selection, not causation. The
event-time check is the closest thing to a causal read but is underpowered
(monthly 1st-of-month snapshots; few in-panel openings).

Run (from anywhere):
    python pipeline/07_analyze_dc_lmp.py
"""

import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT       = Path(__file__).resolve().parent.parent
DB_FILE    = ROOT / "data" / "nj_lmp.db"
DC_JSON    = ROOT / "ui" / "data_centers.json"
OUT_CSV    = ROOT / "data" / "outputs" / "nj_node_lmp_vs_dc.csv"

NEAR_MI    = 10        # "near a data center" threshold for the event-time check
EVENT_YEARS = range(2021, 2024)   # DC openings with enough pre/post in-panel


def haversine_vec(lat, lon, lats, lons):
    """Miles from one point to arrays of points."""
    R = 3958.8
    p = math.pi / 180
    dlat = (lats - lat) * p
    dlon = (lons - lon) * p
    a = (np.sin(dlat / 2) ** 2
         + np.cos(lat * p) * np.cos(lats * p) * np.sin(dlon / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(a))


def load_nodes(conn) -> pd.DataFrame:
    """Node location = centroid of ZIP centroids that map to it."""
    zips = pd.read_sql(
        "SELECT zip, zip_lat, zip_lon, nearest_node, node_zone FROM zips", conn)
    return (zips.groupby("nearest_node")
                .agg(lat=("zip_lat", "mean"), lon=("zip_lon", "mean"),
                     zone=("node_zone", "first"), n_zips=("zip", "size"))
                .reset_index().rename(columns={"nearest_node": "node"}))


def load_premium(conn) -> pd.DataFrame:
    """Per (node, date) locational premium = node LMP - statewide mean that date."""
    lmp = pd.read_sql("SELECT node, date, lmp FROM lmp_daily", conn)
    state_mean = lmp.groupby("date")["lmp"].transform("mean")
    lmp["premium"] = lmp["lmp"] - state_mean
    lmp["yr"] = lmp["date"].str.slice(0, 4).astype(int)
    return lmp


def pearson(a: pd.Series, b: pd.Series) -> float:
    g = pd.concat([a, b], axis=1).dropna()
    return float(g.corr().iloc[0, 1]) if len(g) > 2 else float("nan")


def main() -> None:
    conn = sqlite3.connect(DB_FILE)
    nodes = load_nodes(conn)
    prem = load_premium(conn)
    conn.close()

    dc = json.loads(DC_JSON.read_text(encoding="utf-8"))
    dclat = np.array([d["lat"] for d in dc], dtype=float)
    dclon = np.array([d["lon"] for d in dc], dtype=float)
    dcyear = np.array([d.get("start_year") or 9999 for d in dc], dtype=float)

    # Distance to nearest DC and count within NEAR_MI for every node.
    dists = nodes.apply(
        lambda r: haversine_vec(r["lat"], r["lon"], dclat, dclon), axis=1)
    nodes["dist_dc_mi"]   = dists.apply(np.min)
    nodes["dc_within_10"] = dists.apply(lambda d: int(np.sum(d <= NEAR_MI)))

    # Annual-mean premium per node, wide.
    ann = (prem.groupby(["node", "yr"])["premium"].mean()
               .reset_index()
               .pivot(index="node", columns="yr", values="premium"))
    ann.columns = [f"prem_{c}" for c in ann.columns]
    m = nodes.merge(ann, on="node", how="inner")

    years = sorted(int(c.split("_")[1]) for c in m.columns if c.startswith("prem_"))

    print("=" * 70)
    print("DATA-CENTER PROXIMITY vs WHOLESALE LMP (locational premium)")
    print("=" * 70)
    print(f"located nodes: {len(m)}   data centers: {len(dc)}")
    print(f"distance to nearest DC (mi): min={m.dist_dc_mi.min():.1f}  "
          f"median={m.dist_dc_mi.median():.1f}  max={m.dist_dc_mi.max():.1f}")
    print(f"nodes within {NEAR_MI} mi of a DC: {(m.dist_dc_mi <= NEAR_MI).sum()}"
          f" / {len(m)}")

    # 1. Cross-sectional correlation per year (negative => closer means higher).
    print("\n--- Correlation(distance-to-DC, locational premium) by year ---")
    print("    (negative = nodes closer to data centers carry a higher premium)")
    for y in years:
        col = f"prem_{y}"
        print(f"  {y}: n={m[col].notna().sum():3d}  "
              f"Pearson = {pearson(m['dist_dc_mi'], m[col]):+.3f}")

    # 2. Effect size: premium by proximity band (recent years).
    print("\n--- Locational premium ($/MWh above statewide mean) by proximity band ---")
    m["band"] = pd.cut(m["dist_dc_mi"], [0, 5, 10, 20, 1e9],
                       labels=["<5mi", "5-10mi", "10-20mi", ">20mi"])
    band_years = [y for y in (2022, 2024, 2026) if f"prem_{y}" in m.columns]
    for y in band_years:
        t = m.groupby("band", observed=True)[f"prem_{y}"].mean()
        print(f"  {y}: " + "  ".join(f"{b}={t[b]:+.2f}" for b in t.index))

    # 3. Within-zone (controls for the obvious urban-zone confound).
    print("\n--- Within-zone correlation(distance, premium), latest year ---")
    ly = f"prem_{years[-1]}"
    for z, gz in m.groupby("zone"):
        if gz[ly].notna().sum() >= 8:
            print(f"  {z:6s}: n={gz[ly].notna().sum():3d}  "
                  f"Pearson = {pearson(gz['dist_dc_mi'], gz[ly]):+.3f}")

    # 4. Growth of the premium, early -> late.
    y0, y1 = f"prem_{years[0]}", f"prem_{years[-1]}"
    g = m[["dist_dc_mi", y0, y1]].dropna().copy()
    g["prem_growth"] = g[y1] - g[y0]
    print(f"\n--- Premium growth {years[0]}->{years[-1]} vs distance-to-DC ---")
    print(f"  Pearson = {pearson(g['dist_dc_mi'], g['prem_growth']):+.3f}  (n={len(g)})")

    # 5. Event-time check: DC openings during the panel.
    print(f"\n--- Event-time: nodes <= {NEAR_MI} mi from a DC that opened in "
          f"{EVENT_YEARS.start}-{EVENT_YEARS.stop-1} ---")
    print("    premium change (after - before opening year), near vs far nodes")
    long = prem.groupby(["node", "yr"])["premium"].mean().reset_index()
    long = long.merge(nodes[["node", "lat", "lon"]], on="node")
    for oy in EVENT_YEARS:
        # data centers that opened in year oy
        idx = np.where(dcyear == oy)[0]
        if len(idx) == 0:
            continue
        oy_lat, oy_lon = dclat[idx], dclon[idx]
        def near_open(r):
            return bool(np.any(haversine_vec(r["lat"], r["lon"], oy_lat, oy_lon) <= NEAR_MI))
        long["near"] = long.apply(near_open, axis=1)
        pre  = long[long.yr.between(oy - 2, oy - 1)].groupby(["node", "near"])["premium"].mean()
        post = long[long.yr.between(oy + 1, oy + 2)].groupby(["node", "near"])["premium"].mean()
        delta = (post - pre).reset_index(name="delta")
        near_d = delta[delta["near"]]["delta"].mean()
        far_d  = delta[~delta["near"]]["delta"].mean()
        n_near = (delta["near"]).sum()
        if pd.notna(near_d) and pd.notna(far_d):
            print(f"  opened {oy} ({len(idx)} DC): near delta={near_d:+.2f}  "
                  f"far delta={far_d:+.2f}  diff-in-diff={near_d - far_d:+.2f}  "
                  f"(n_near={n_near})")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    keep = ["node", "zone", "lat", "lon", "dist_dc_mi", "dc_within_10"] + \
           [f"prem_{y}" for y in years]
    m[keep].sort_values("dist_dc_mi").to_csv(OUT_CSV, index=False,
                                             float_format="%.3f")
    print(f"\nWrote {OUT_CSV}")

    print("\n--- Read with care ---")
    print("  Proximity is endogenous: data centers site in existing load")
    print("  pockets, so a negative distance-premium link is partly siting")
    print("  selection. Effect sizes here are in $/MWh of WHOLESALE premium;")
    print("  divide by ~10 for cents/kWh, then note retail rates are set")
    print("  utility-wide, so even a real wholesale premium is socialized")
    print("  across the territory rather than billed to the nearest ZIP.")


if __name__ == "__main__":
    main()
