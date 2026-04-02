"""
Convert nj_zip_lmp_jan1_2020_2025.csv to ui/nj_zip_info.json
for the interactive map.
"""

import json
import pandas as pd
import os

# NJ County mapping by ZIP prefix
NJ_COUNTY_MAP = {
    "07": "Bergen", "071": "Bergen", "072": "Bergen",
    "073": "Essex", "074": "Hudson", "075": "Hudson",
    "076": "Bergen", "077": "Bergen", "078": "Bergen",
    "080": "Atlantic", "081": "Atlantic", "082": "Atlantic",
    "083": "Burlington", "084": "Camden", "085": "Camden",
    "086": "Cape May", "087": "Cumberland", "088": "Cumberland",
    "089": "Gloucester", "0800": "Atlantic", "0801": "Atlantic",
    "0802": "Atlantic", "0803": "Burlington", "0804": "Camden",
    "0805": "Cape May", "0806": "Cape May", "0807": "Cumberland",
    "0808": "Cumberland", "0809": "Gloucester", "0810": "Atlantic",
    "0811": "Atlantic", "0812": "Atlantic", "0813": "Burlington",
    "0814": "Camden", "0815": "Camden", "0816": "Cape May",
    "0817": "Cumberland", "0818": "Cumberland", "0819": "Gloucester",
    "0820": "Monmouth", "0821": "Monmouth", "0822": "Monmouth",
    "0823": "Monmouth", "0824": "Monmouth", "0825": "Monmouth",
    "0826": "Monmouth", "0827": "Monmouth", "0828": "Morris",
    "0829": "Morris", "0830": "Morris", "0831": "Morris",
    "0832": "Morris", "0833": "Passaic", "0834": "Passaic",
    "0835": "Passaic", "0836": "Passaic", "0837": "Passaic",
    "0838": "Passaic", "0839": "Passaic", "0840": "Sussex",
    "0841": "Sussex", "0842": "Sussex", "0843": "Hunterdon",
    "0844": "Hunterdon", "0845": "Somerset", "0846": "Middlesex",
    "0847": "Middlesex", "0848": "Middlesex", "0849": "Mercer",
    "0850": "Mercer", "0851": "Mercer", "0852": "Middlesex",
    "0853": "Mercer", "0854": "Mercer", "0855": "Mercer",
    "0856": "Union", "0857": "Union", "0858": "Union",
    "0859": "Union", "0860": "Union", "0861": "Monmouth",
}

def get_county_for_zip(zip_code):
    """Return county name for a given 5-digit ZIP code."""
    zip_str = str(int(zip_code)).zfill(5)
    # Try exact 4-digit match first
    if zip_str[:4] in NJ_COUNTY_MAP:
        return NJ_COUNTY_MAP[zip_str[:4]]
    # Try 3-digit
    if zip_str[:3] in NJ_COUNTY_MAP:
        return NJ_COUNTY_MAP[zip_str[:3]]
    # Default based on first digit
    if zip_str[0] == "0":
        if zip_str[1] == "7":
            return "North Jersey"
        elif zip_str[1] == "8":
            return "South Jersey"
    return None

def build_ui_json(csv_path="nj_zip_lmp_jan1_2020_2025.csv", output_path="ui/nj_zip_info.json"):
    """Read zip LMP CSV and generate UI JSON with yearly data."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    
    df = pd.read_csv(csv_path)
    payload = {}
    
    for _, row in df.iterrows():
        zip_code = str(int(row["zip"])).zfill(5)
        
        yearly_lmp = {}
        for year in range(2020, 2026):
            col = f"lmp_{year}"
            if col in df.columns:
                val = row[col]
                yearly_lmp[str(year)] = round(float(val), 3) if pd.notna(val) else None
        
        pct_chg = row.get("pct_chg_2020_2025")
        pct_chg = round(float(pct_chg), 3) if pd.notna(pct_chg) else None
        
        lmp_2020 = yearly_lmp.get("2020")
        lmp_2025 = yearly_lmp.get("2025")
        
        payload[zip_code] = {
            "county": get_county_for_zip(zip_code),
            "avg_lmp_2020": lmp_2020,
            "avg_lmp_2025": lmp_2025,
            "pct_change": pct_chg,
            "yearly_lmp": yearly_lmp,
            "selected_year": "2025",
            "nearest_node": str(row.get("nearest_node", "")),
            "node_zone": str(row.get("node_zone", "")),
            "dist_miles": float(row.get("dist_miles", 0)) if pd.notna(row.get("dist_miles")) else None,
            "notes": f"Nearest PJM node: {row.get('nearest_node', 'N/A')} ({row.get('node_zone', 'N/A')}) — {row.get('dist_miles', 'N/A')} miles away"
        }
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    
    print(f"Generated {output_path}: {len(payload)} ZIPs with yearly LMP data + county names")

if __name__ == "__main__":
    build_ui_json()
