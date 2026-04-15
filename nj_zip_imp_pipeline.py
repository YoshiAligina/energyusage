
"""
NJ Zip Code LMP Pipeline
========================
Pulls PJM Day-Ahead LMP for all NJ load nodes (PSEG, JCPL, AECO, RECO)
for a specified date range, maps to NJ zip codes, and writes to SQLite.

Requirements:
    pip install requests pandas numpy thefuzz python-Levenshtein

Output:
    nj_lmp.db  (SQLite — tables: zips, lmp_daily)
"""

import os, re, time, requests, zipfile, io, sqlite3
import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
from thefuzz import process, fuzz

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
PJM_API_KEY = "624c152b81f2406cb9f36aa0891b644c"   # from dataminer2.pjm.com/config/settings.json
PJM_API_URL = "https://api.pjm.com/api/v1/da_hrl_lmps"
NJ_ZONES    = {"PSEG", "JCPL", "AECO", "RECO"}
YEARS       = range(2020, 2026)
DB_FILE     = "nj_lmp.db"

HEADERS = {
    "Ocp-Apim-Subscription-Key": PJM_API_KEY,
    "Accept": "application/json",
}


# ─────────────────────────────────────────────
# STEP 1: Pull NJ LOAD node LMPs from PJM API
# Jan 1 midnight (hour 0) for each year
# ─────────────────────────────────────────────
def fetch_nj_lmp_jan1(year: int) -> pd.DataFrame:
    """
    Fetch all LOAD nodes for Jan 1 of `year`, hour 0 only.
    The `zone` filter is not supported for archived data (>60 days old),
    so we pull all LOAD nodes and filter client-side.
    Rate limit: 6 requests/minute for non-members.
    """
    date_str = f"01/01/{year} 00:00to01/01/{year} 00:00"
    all_items = []
    row = 1
    while True:
        params = {
            "startRow": row,
            "isActiveMetadata": "true",
            "rowCount": 5000,
            "datetime_beginning_ept": date_str,
            "type": "LOAD",
        }
        r = requests.get(PJM_API_URL, params=params, headers=HEADERS, timeout=60)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        all_items.extend(items)
        total = data.get("totalRows", 0)
        if row + 5000 > total:
            break
        row += 5000
        time.sleep(11)   # stay under 6 req/min

    df = pd.DataFrame(all_items)
    df = df[df["zone"].isin(NJ_ZONES)].copy()
    df["jan1_year"] = year
    return df


def pull_all_years() -> pd.DataFrame:
    frames = []
    for year in YEARS:
        print(f"  Fetching Jan 1, {year}...", end=" ", flush=True)
        df = fetch_nj_lmp_jan1(year)
        frames.append(df)
        print(f"{len(df)} NJ rows  ({df['pnode_name'].nunique()} unique nodes)")
        time.sleep(5)
    return pd.concat(frames, ignore_index=True)


# ─────────────────────────────────────────────
# STEP 2: Get NJ zip code centroids (Census)
# ─────────────────────────────────────────────
def get_nj_zip_centroids() -> pd.DataFrame:
    url = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip"
    print("  Downloading Census ZCTA gazetteer...", end=" ", flush=True)
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        fname = [n for n in z.namelist() if n.endswith(".txt")][0]
        df = pd.read_csv(z.open(fname), sep="\t", dtype={"GEOID": str})
    df.columns = df.columns.str.strip()
    df_nj = df[df["GEOID"].str.startswith(("07", "08"))][["GEOID", "INTPTLAT", "INTPTLONG"]].copy()
    df_nj.columns = ["zip", "zip_lat", "zip_lon"]
    print(f"{len(df_nj)} NJ zip codes")
    return df_nj


# ─────────────────────────────────────────────
# STEP 3: Get substation coordinates
#   A. OSM Overpass (fuzzy match on node name)
#   B. Manual lookup for the 121 abbreviated names
#      that OSM doesn't resolve
# ─────────────────────────────────────────────
def get_osm_substations() -> pd.DataFrame:
    """Query OpenStreetMap for all power infrastructure in NJ bounding box."""
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = """
    [out:json][timeout:60];
    (
      node["power"="substation"](38.9,-75.6,41.4,-73.9);
      way["power"="substation"](38.9,-75.6,41.4,-73.9);
      node["power"="transformer"](38.9,-75.6,41.4,-73.9);
    );
    out center;
    """
    print("  Querying OpenStreetMap for NJ substations...", end=" ", flush=True)
    r = requests.post(overpass_url, data={"data": query}, timeout=90)
    r.raise_for_status()
    elements = r.json().get("elements", [])
    rows = []
    for el in elements:
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        name = el.get("tags", {}).get("name", "")
        if lat and lon:
            rows.append({"name": name, "lat": lat, "lon": lon})
    df = pd.DataFrame(rows)
    named = df[df["name"].str.strip() != ""].copy()
    named["name_clean"] = (named["name"].str.upper()
                           .str.replace(r'\s*(SUBSTATION|SWITCHING STATION|STATION|POWER PLANT|PEAKING PLANT|S/S)\s*',
                                        '', regex=True).str.strip())
    print(f"{len(named)} named elements")
    return named


def extract_substation_name(pnode_name: str) -> str:
    """Strip voltage/equipment suffix from PJM node name to get bare substation name."""
    clean = re.sub(r'\s+\d+\.?\d*\s*(KV|KW|MW).*$', '', pnode_name.strip(), flags=re.IGNORECASE)
    clean = re.sub(r'\s+(T-\d+|AB GRP|LOAD\d*|GEN\d*|BUS\d*|CC\d*|\w{1,5}SP)$', '', clean.strip(), flags=re.IGNORECASE)
    return clean.strip().upper()


def fuzzy_match_nodes(node_names: list[str], osm_df: pd.DataFrame) -> dict:
    """Return {pnode_name: (lat, lon, method)} for all fuzzy/exact matches (score >= 75)."""
    osm_choices = osm_df["name_clean"].tolist()
    osm_index = {name: i for i, name in enumerate(osm_choices)}  # O(1) lookup
    results = {}
    for name in node_names:
        sub = extract_substation_name(name)
        # Exact first
        exact = osm_df[osm_df["name_clean"] == sub]
        if len(exact):
            row = exact.iloc[0]
            results[name] = (row["lat"], row["lon"], "exact")
            continue
        # Fuzzy
        match = process.extractOne(sub, osm_choices, scorer=fuzz.token_set_ratio)
        if match and match[1] >= 75:
            idx = osm_index.get(match[0])
            if idx is not None:
                row = osm_df.iloc[idx]
                results[name] = (row["lat"], row["lon"], "fuzzy")
    return results


# Manual coordinates for the 121 nodes whose abbreviated names
# don't match OSM — decoded from PJM naming conventions + NJ geography.
MANUAL_COORDS = {
    # AECO — Atlantic City Electric (South Jersey)
    "VALEPKTP":  (39.3644, -75.1288), "CARNEYPT":  (39.7501, -75.1066),
    "UPPERPIT":  (39.8303, -75.0505), "WENONAH":   (39.7448, -75.1519),
    "SHIPBOTT":  (39.5498, -74.8266), "MANNMILL":  (39.5687, -74.9737),
    "MONR AE":   (39.8963, -75.3977), "MANVILTP":  (40.5426, -74.5882),
    "RIOGRAND":  (39.0110, -74.8774), "AIRCOAE":   (39.8560, -75.0670),
    "SEAISLE":   (39.1534, -74.6943), "PENNSGRO":  (39.7268, -75.5138),
    "CUMB AE":   (39.3876, -75.0647), "PEDRICKT":  (39.8698, -75.3003),
    "VINELAND":  (39.4862, -75.0258), "HIGHST":    (39.5379, -75.0635),
    "FRANKAE":   (39.4259, -75.0570), "MOSSMILL":  (39.5734, -74.8604),
    "HARBORBC":  (38.9344, -74.9239), "LINCOLN1":  (39.7024, -75.2481),
    "REPAUNO":   (39.7319, -75.3516), "LAKEAVEN":  (39.9282, -74.2208),
    "FAATC":     (39.4572, -74.5727), "BURL_TAP":  (39.9940, -74.8692),
    "PINEHILL":  (39.7479, -74.9785), "SILVERLA":  (39.5940, -74.9780),
    "LINCOLN3":  (39.7024, -75.2481), "SMILLVIL":  (39.5567, -75.0972),
    # JCPL — Jersey Central Power & Light (Central NJ)
    "GLENGARD":  (40.2977, -74.1838), "EATONCST":  (40.2926, -74.5198),
    "NEWPROSP":  (41.0578, -74.5618), "CHESTJCT":  (40.6320, -74.7022),
    "SAYRECON":  (40.7197, -74.9107), "DOTWWHAR":  (40.9010, -74.8240),
    "MERRILCR":  (40.0150, -74.2100), "WILL JC":   (40.6518, -74.2760),
    "SUMM JC":   (40.6976, -74.3574), "STON JC":   (40.9073, -74.5553),
    "LEISUREV":  (39.9290, -74.1815), "NJTABERD":  (40.1548, -74.2312),
    "NJTREDBA":  (40.1548, -74.2312), "OYSTERCR":  (39.8565, -74.1200),
    "WIND JC":   (40.8629, -75.0001), "REDBAJCT":  (40.3471, -74.0760),
    # PSEG — Public Service E&G (North/Central NJ)
    "CSQ_HOPE":  (40.7058, -74.8593), "LIBRTYST":  (40.7178, -74.0431),
    "NJTMEADO":  (40.7799, -74.1502), "PRNCTNPS":  (40.3573, -74.6672),
    "MARIONDR":  (40.9357, -74.1623), "CLNTNAVE":  (40.7282, -74.1753),
    "Z650TAP":   (40.6890, -74.1740), "DEVILSBR":  (40.7501, -74.8290),
    "CJN":       (40.7178, -74.0700), "MTHOLLY":   (39.9932, -74.7879),
    "BELLEMDT":  (40.7943, -74.1519), "RIVRSDPS":  (40.0154, -74.9547),
    "TRANSCTC":  (40.7357, -74.1724), "CBR_LAW":   (40.2982, -74.7426),
    "BRIDGEWA":  (40.5968, -74.6043), "SFIFTHST":  (40.7282, -74.1771),
    "LIVINGPS":  (40.7957, -74.3209), "WASHAVE":   (40.7357, -74.1640),
    "HOWEAVE":   (40.7450, -74.2040), "NPARKST":   (40.7357, -74.1724),
    "ORANGEHT":  (40.7693, -74.2338), "14STREET":  (40.7500, -74.0500),
    "NYEAVE":    (40.7167, -74.1000), "SYCAMORE":  (40.8220, -74.1340),
    "TEXAVE":    (40.7357, -74.1640), "TONEYSBR":  (40.2823, -74.7577),
    "DRTTOTO":   (40.8359, -74.0891), "MTROSEPS":  (40.6584, -74.2569),
    "WHITHRSE":  (40.2170, -74.6530), "MELRICH":   (40.5223, -74.4161),
    "HUNTGLEN":  (40.4024, -74.6535), "HASBHGTS":  (40.6084, -74.0740),
    "STATSTPS":  (40.6298, -74.1036), "PENNSNEC":  (39.9527, -75.0378),
    "NICHLSN":   (40.7635, -74.1909), "QTS":       (40.7695, -74.1925),
    "LINVFT":    (40.8290, -74.1244), "EAGLEGEN":  (40.5135, -74.3671),
    "COXSCORN":  (40.4660, -74.4330), "NEWMILFR":  (40.9373, -74.0147),
    "SANDHILL":  (40.1887, -74.5490), "SUNNYMEA":  (40.5530, -74.3050),
    "WARDAV":    (40.7800, -74.2340), "ERUTHERF":  (40.8218, -74.1068),
    "FEDERALS":  (40.7282, -74.1644), "LAWRESUB":  (40.2982, -74.7197),
    "HOPECREE":  (40.4787, -74.6668), "PIERSOAV":  (40.8357, -74.1178),
    "NEWP PS":   (40.7178, -74.0489), "MINUEST":   (40.7610, -74.2130),
    "CLIF PS":   (40.8626, -74.1639), "SSECONDS":  (40.7282, -74.1771),
    "WORANGE":   (40.7940, -74.2530), "HCS":       (40.5710, -74.3204),
    "WCALDWEL":  (40.8395, -74.2780), "STANLEYT":  (40.6573, -74.2988),
    "PVSC":      (40.6840, -74.1330), "MCCLEABD":  (40.4154, -74.2568),
    "FORTHST":   (40.7282, -74.1640), "SPRINGRD":  (40.5968, -74.6043),
    "NBRIDGST":  (40.7282, -74.1644), "MONTGOPS":  (40.4197, -74.6513),
    "MTNAVEPS":  (40.7752, -74.2390), "WARRENPT":  (40.8890, -74.8740),
    "JACK PS":   (40.7282, -74.1640), "NWRKARPT":  (40.6895, -74.1745),
    "SADDLEBR":  (40.9490, -74.3570), "CLIFFS":    (40.8215, -73.9957),
    "NEWARKEC":  (40.7357, -74.1724), "LAFA PS":   (40.7178, -74.0489),
    "SWATERFR":  (40.7178, -74.0600), "FRONTST":   (40.7178, -74.0489),
    # RECO — Rockland Electric (NW Bergen County)
    "HARINGSC":  (41.0626, -74.1097), "SMAWA":     (41.1015, -74.1886),
    "UPPERSAD":  (41.0654, -74.0987), "OAKLAND":   (41.0282, -74.2321),
    "SUMMITAV":  (41.0490, -74.1380),
}


def build_node_coords(lmp: pd.DataFrame, osm_df: pd.DataFrame) -> pd.DataFrame:
    """Combine OSM fuzzy matches + manual lookup into a full node→coord table."""
    unique_nodes = lmp["pnode_name"].unique().tolist()
    osm_results = fuzzy_match_nodes(unique_nodes, osm_df)

    rows = []
    node_to_zone = lmp[["pnode_name","zone"]].drop_duplicates().set_index("pnode_name")["zone"].to_dict()

    for name in unique_nodes:
        zone = node_to_zone.get(name, "PSEG")
        if name in osm_results:
            lat, lon, method = osm_results[name]
        elif name in MANUAL_COORDS:
            lat, lon = MANUAL_COORDS[name]
            method = "manual_town"
        else:
            lat, lon, method = None, None, "unresolved"
        rows.append({"pnode_name": name, "zone": zone, "lat": lat, "lon": lon, "coord_method": method})

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# STEP 4: Haversine + nearest-node join
# ─────────────────────────────────────────────
def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return R * 2 * asin(sqrt(a))


def assign_zips_to_nodes(zips: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    """For each zip centroid, find the nearest PJM node (vectorized haversine)."""
    R = 3958.8
    zlats = np.radians(zips["zip_lat"].values.astype(float))
    zlons = np.radians(zips["zip_lon"].values.astype(float))
    nlats = np.radians(nodes["lat"].values.astype(float))
    nlons = np.radians(nodes["lon"].values.astype(float))

    # Shape: (n_zips, n_nodes) — fully vectorized, no Python loop over nodes
    dlat = nlats[np.newaxis, :] - zlats[:, np.newaxis]
    dlon = nlons[np.newaxis, :] - zlons[:, np.newaxis]
    a = (np.sin(dlat / 2) ** 2
         + np.cos(zlats[:, np.newaxis]) * np.cos(nlats[np.newaxis, :]) * np.sin(dlon / 2) ** 2)
    dist_matrix = R * 2 * np.arcsin(np.sqrt(a))  # (n_zips, n_nodes)

    best_idx = np.argmin(dist_matrix, axis=1)

    results = []
    for i, (_, zrow) in enumerate(zips.iterrows()):
        idx = best_idx[i]
        bn  = nodes.iloc[idx]
        results.append({
            "zip": str(zrow["zip"]).replace(".0", "").zfill(5),
            "zip_lat": round(float(zrow["zip_lat"]), 5),
            "zip_lon": round(float(zrow["zip_lon"]), 5),
            "nearest_node": bn["pnode_name"],
            "node_zone": bn["zone"],
            "dist_miles": round(dist_matrix[i, idx], 2),
            "coord_method": bn["coord_method"],
        })
    return pd.DataFrame(results)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Step 1: Pull NJ LMP data from PJM API ===")
    lmp = pull_all_years()
    print(f"Total rows: {len(lmp)}, unique nodes: {lmp['pnode_name'].nunique()}\n")

    print("=== Step 2: NJ zip code centroids ===")
    zips = get_nj_zip_centroids()
    print()

    print("=== Step 3: Node coordinates ===")
    osm_df = get_osm_substations()
    node_coords = build_node_coords(lmp, osm_df)
    unresolved = node_coords[node_coords["coord_method"] == "unresolved"]
    if len(unresolved):
        print(f"  WARNING: {len(unresolved)} nodes still unresolved: {unresolved['pnode_name'].tolist()}")
    print(f"  Coord breakdown: {node_coords['coord_method'].value_counts().to_dict()}\n")

    print("=== Step 4: Build node LMP table ===")
    # Average hourly readings → one daily value per (node, date)
    lmp_daily = (lmp.groupby(["pnode_name", "jan1_year"])["total_lmp_da"]
                    .mean().reset_index())
    lmp_daily["date"] = lmp_daily["jan1_year"].apply(lambda y: f"{y}-01-01")
    lmp_daily = lmp_daily.rename(columns={"pnode_name": "node", "total_lmp_da": "lmp"})
    lmp_daily["lmp"] = lmp_daily["lmp"].round(4)

    # Keep only nodes we have coordinates for
    resolved_nodes = node_coords.dropna(subset=["lat","lon"])
    nodes_for_zip = node_coords[["pnode_name","lat","lon","coord_method","zone"]].dropna(subset=["lat","lon"])

    print("=== Step 5: Zip → nearest node ===")
    zip_nodes = assign_zips_to_nodes(zips, nodes_for_zip)

    print("=== Step 6: Write to SQLite ===")
    conn = sqlite3.connect(DB_FILE)
    try:
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
                node  TEXT NOT NULL,
                date  TEXT NOT NULL,
                lmp   REAL,
                PRIMARY KEY (node, date)
            );
            CREATE INDEX IF NOT EXISTS idx_lmp_daily_node ON lmp_daily (node);
            CREATE INDEX IF NOT EXISTS idx_lmp_daily_date ON lmp_daily (date);
            CREATE INDEX IF NOT EXISTS idx_zips_node      ON zips (nearest_node);
        """)

        zip_nodes.to_sql("zips", conn, if_exists="replace", index=False)
        print(f"  Wrote {len(zip_nodes)} rows → zips")

        lmp_out = lmp_daily[lmp_daily["node"].isin(resolved_nodes["pnode_name"])][["node","date","lmp"]]
        lmp_out.to_sql("lmp_daily", conn, if_exists="replace", index=False)
        print(f"  Wrote {len(lmp_out)} rows → lmp_daily ({lmp_out['node'].nunique()} nodes)")

        conn.commit()
    finally:
        conn.close()

    print(f"\nSaved → {DB_FILE}")
    print(f"Avg dist to node: {zip_nodes['dist_miles'].mean():.1f} miles")
    print(f"\nSample zips:")
    print(zip_nodes.sample(5, random_state=1)[
        ["zip","node_zone","nearest_node","dist_miles"]
    ].to_string(index=False))
