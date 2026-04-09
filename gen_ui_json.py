"""
Convert nj_zip_lmp_jan1_2020_2025.csv to ui/nj_zip_info.json
for the interactive map.
"""

import json
import pandas as pd
import os

NJ_ZIP_COUNTY = {
    # Bergen
    "07010": "Bergen", "07020": "Bergen", "07022": "Bergen", "07024": "Bergen",
    "07026": "Bergen", "07031": "Bergen", "07057": "Bergen", "07070": "Bergen",
    "07071": "Bergen", "07072": "Bergen", "07073": "Bergen", "07074": "Bergen",
    "07075": "Bergen", "07401": "Bergen", "07407": "Bergen", "07410": "Bergen",
    "07417": "Bergen", "07423": "Bergen", "07430": "Bergen", "07432": "Bergen",
    "07436": "Bergen", "07446": "Bergen", "07450": "Bergen", "07452": "Bergen",
    "07458": "Bergen", "07463": "Bergen", "07481": "Bergen",
    "07601": "Bergen", "07603": "Bergen", "07604": "Bergen", "07605": "Bergen",
    "07606": "Bergen", "07607": "Bergen", "07608": "Bergen", "07620": "Bergen",
    "07621": "Bergen", "07624": "Bergen", "07626": "Bergen", "07627": "Bergen",
    "07628": "Bergen", "07630": "Bergen", "07631": "Bergen", "07632": "Bergen",
    "07640": "Bergen", "07641": "Bergen", "07642": "Bergen", "07643": "Bergen",
    "07644": "Bergen", "07645": "Bergen", "07646": "Bergen", "07647": "Bergen",
    "07648": "Bergen", "07649": "Bergen", "07650": "Bergen", "07652": "Bergen",
    "07656": "Bergen", "07657": "Bergen", "07660": "Bergen", "07661": "Bergen",
    "07662": "Bergen", "07663": "Bergen", "07666": "Bergen", "07670": "Bergen",
    "07675": "Bergen", "07676": "Bergen", "07677": "Bergen",
    # Essex
    "07003": "Essex", "07004": "Essex", "07006": "Essex", "07009": "Essex",
    "07017": "Essex", "07018": "Essex", "07021": "Essex", "07028": "Essex",
    "07039": "Essex", "07040": "Essex", "07041": "Essex", "07042": "Essex",
    "07043": "Essex", "07044": "Essex", "07050": "Essex", "07052": "Essex",
    "07068": "Essex", "07078": "Essex", "07079": "Essex",
    "07102": "Essex", "07103": "Essex", "07104": "Essex", "07105": "Essex",
    "07106": "Essex", "07107": "Essex", "07108": "Essex", "07109": "Essex",
    "07110": "Essex", "07111": "Essex", "07112": "Essex", "07114": "Essex",
    # Hudson
    "07002": "Hudson", "07029": "Hudson", "07030": "Hudson", "07032": "Hudson",
    "07047": "Hudson", "07086": "Hudson", "07087": "Hudson", "07093": "Hudson",
    "07094": "Hudson",
    "07302": "Hudson", "07304": "Hudson", "07305": "Hudson", "07306": "Hudson",
    "07307": "Hudson", "07310": "Hudson", "07311": "Hudson",
    # Middlesex
    "07001": "Middlesex", "07008": "Middlesex", "07064": "Middlesex",
    "07067": "Middlesex", "07077": "Middlesex", "07080": "Middlesex",
    "07095": "Middlesex",
    # Morris
    "07005": "Morris", "07034": "Morris", "07035": "Morris", "07045": "Morris",
    "07046": "Morris", "07054": "Morris", "07058": "Morris", "07082": "Morris",
    "07405": "Morris", "07440": "Morris", "07444": "Morris", "07457": "Morris",
    "07801": "Morris", "07803": "Morris", "07828": "Morris", "07834": "Morris",
    "07836": "Morris", "07842": "Morris", "07847": "Morris", "07849": "Morris",
    "07850": "Morris", "07852": "Morris", "07853": "Morris", "07856": "Morris",
    "07857": "Morris", "07866": "Morris", "07869": "Morris", "07870": "Morris",
    "07876": "Morris", "07878": "Morris", "07885": "Morris",
    "07926": "Morris", "07927": "Morris", "07928": "Morris", "07930": "Morris",
    "07932": "Morris", "07933": "Morris", "07935": "Morris", "07936": "Morris",
    "07939": "Morris", "07940": "Morris", "07945": "Morris", "07946": "Morris",
    "07950": "Morris", "07960": "Morris", "07961": "Morris", "07970": "Morris",
    "07976": "Morris", "07980": "Morris", "07981": "Morris",
    # Passaic
    "07011": "Passaic", "07012": "Passaic", "07013": "Passaic", "07014": "Passaic",
    "07055": "Passaic", "07403": "Passaic", "07420": "Passaic", "07421": "Passaic",
    "07422": "Passaic", "07424": "Passaic", "07435": "Passaic", "07438": "Passaic",
    "07442": "Passaic", "07456": "Passaic", "07465": "Passaic", "07470": "Passaic",
    "07480": "Passaic",
    "07501": "Passaic", "07502": "Passaic", "07503": "Passaic", "07504": "Passaic",
    "07505": "Passaic", "07506": "Passaic", "07508": "Passaic", "07512": "Passaic",
    "07513": "Passaic", "07514": "Passaic", "07522": "Passaic", "07524": "Passaic",
    # Union
    "07016": "Union", "07023": "Union", "07027": "Union", "07033": "Union",
    "07036": "Union", "07060": "Union", "07062": "Union", "07063": "Union",
    "07065": "Union", "07066": "Union", "07076": "Union", "07081": "Union",
    "07083": "Union", "07088": "Union", "07090": "Union", "07092": "Union",
    "07201": "Union", "07202": "Union", "07203": "Union", "07204": "Union",
    "07205": "Union", "07206": "Union", "07208": "Union",
    "07901": "Union", "07922": "Union", "07974": "Union",
    # Somerset
    "07059": "Somerset", "07069": "Somerset",
    "07920": "Somerset", "07921": "Somerset", "07924": "Somerset",
    "07931": "Somerset", "07934": "Somerset", "07977": "Somerset",
    # Sussex
    "07416": "Sussex", "07418": "Sussex", "07419": "Sussex", "07439": "Sussex",
    "07460": "Sussex", "07461": "Sussex", "07462": "Sussex",
    "07821": "Sussex", "07822": "Sussex", "07826": "Sussex", "07827": "Sussex",
    "07843": "Sussex", "07848": "Sussex", "07851": "Sussex", "07860": "Sussex",
    "07871": "Sussex", "07874": "Sussex", "07881": "Sussex",
    # Warren
    "07820": "Warren", "07823": "Warren", "07825": "Warren", "07832": "Warren",
    "07833": "Warren", "07838": "Warren", "07840": "Warren", "07844": "Warren",
    "07846": "Warren", "07863": "Warren", "07865": "Warren", "07880": "Warren",
    "07882": "Warren",
    # Hunterdon
    "07830": "Hunterdon", "07831": "Hunterdon", "07979": "Hunterdon",
    # Monmouth
    "07701": "Monmouth", "07702": "Monmouth", "07703": "Monmouth", "07704": "Monmouth",
    "07711": "Monmouth", "07712": "Monmouth", "07716": "Monmouth", "07717": "Monmouth",
    "07718": "Monmouth", "07719": "Monmouth", "07720": "Monmouth", "07721": "Monmouth",
    "07722": "Monmouth", "07723": "Monmouth", "07724": "Monmouth", "07726": "Monmouth",
    "07727": "Monmouth", "07728": "Monmouth", "07730": "Monmouth", "07731": "Monmouth",
    "07732": "Monmouth", "07733": "Monmouth", "07734": "Monmouth", "07735": "Monmouth",
    "07737": "Monmouth", "07738": "Monmouth", "07739": "Monmouth", "07740": "Monmouth",
    "07746": "Monmouth", "07747": "Monmouth", "07748": "Monmouth", "07750": "Monmouth",
    "07751": "Monmouth", "07753": "Monmouth", "07755": "Monmouth", "07756": "Monmouth",
    "07757": "Monmouth", "07758": "Monmouth", "07760": "Monmouth", "07762": "Monmouth",
    "07764": "Monmouth",
    # --- 08xxx ---
    # Salem
    "08001": "Salem", "08023": "Salem", "08038": "Salem", "08067": "Salem",
    "08069": "Salem", "08070": "Salem", "08072": "Salem", "08079": "Salem",
    "08098": "Salem", "08318": "Salem", "08343": "Salem",
    # Camden
    "08002": "Camden", "08003": "Camden", "08004": "Camden", "08007": "Camden",
    "08009": "Camden", "08012": "Camden", "08021": "Camden", "08026": "Camden",
    "08029": "Camden", "08030": "Camden", "08031": "Camden", "08032": "Camden",
    "08033": "Camden", "08034": "Camden", "08035": "Camden", "08043": "Camden",
    "08045": "Camden", "08049": "Camden", "08059": "Camden", "08078": "Camden",
    "08081": "Camden", "08083": "Camden", "08084": "Camden", "08089": "Camden",
    "08091": "Camden", "08095": "Camden",
    "08102": "Camden", "08103": "Camden", "08104": "Camden", "08105": "Camden",
    "08106": "Camden", "08107": "Camden", "08108": "Camden", "08109": "Camden",
    "08110": "Camden",
    # Burlington
    "08010": "Burlington", "08011": "Burlington", "08015": "Burlington",
    "08016": "Burlington", "08019": "Burlington", "08022": "Burlington",
    "08036": "Burlington", "08041": "Burlington", "08042": "Burlington",
    "08046": "Burlington", "08048": "Burlington", "08052": "Burlington",
    "08053": "Burlington", "08054": "Burlington", "08055": "Burlington",
    "08057": "Burlington", "08060": "Burlington", "08064": "Burlington",
    "08065": "Burlington", "08068": "Burlington", "08073": "Burlington",
    "08075": "Burlington", "08088": "Burlington", "08224": "Burlington",
    "08505": "Burlington", "08511": "Burlington", "08515": "Burlington",
    "08518": "Burlington", "08554": "Burlington", "08562": "Burlington",
    "08640": "Burlington", "08641": "Burlington",
    # Gloucester
    "08014": "Gloucester", "08020": "Gloucester", "08027": "Gloucester",
    "08028": "Gloucester", "08039": "Gloucester", "08051": "Gloucester",
    "08056": "Gloucester", "08061": "Gloucester", "08062": "Gloucester",
    "08063": "Gloucester", "08066": "Gloucester", "08071": "Gloucester",
    "08074": "Gloucester", "08077": "Gloucester", "08080": "Gloucester",
    "08085": "Gloucester", "08086": "Gloucester", "08090": "Gloucester",
    "08093": "Gloucester", "08094": "Gloucester", "08096": "Gloucester",
    "08097": "Gloucester", "08312": "Gloucester", "08322": "Gloucester",
    "08328": "Gloucester", "08344": "Gloucester",
    # Atlantic
    "08037": "Atlantic", "08201": "Atlantic", "08203": "Atlantic",
    "08205": "Atlantic", "08215": "Atlantic", "08217": "Atlantic",
    "08221": "Atlantic", "08223": "Atlantic", "08225": "Atlantic",
    "08232": "Atlantic", "08234": "Atlantic", "08240": "Atlantic",
    "08241": "Atlantic", "08244": "Atlantic",
    "08310": "Atlantic", "08317": "Atlantic", "08319": "Atlantic",
    "08326": "Atlantic", "08330": "Atlantic", "08340": "Atlantic",
    "08341": "Atlantic", "08346": "Atlantic", "08350": "Atlantic",
    "08401": "Atlantic", "08402": "Atlantic", "08403": "Atlantic", "08406": "Atlantic",
    # Cape May
    "08202": "Cape May", "08204": "Cape May", "08210": "Cape May",
    "08212": "Cape May", "08226": "Cape May", "08230": "Cape May",
    "08242": "Cape May", "08243": "Cape May", "08245": "Cape May",
    "08246": "Cape May", "08247": "Cape May", "08248": "Cape May",
    "08251": "Cape May", "08260": "Cape May", "08270": "Cape May",
    "08314": "Cape May",
    # Cumberland
    "08302": "Cumberland", "08311": "Cumberland", "08316": "Cumberland",
    "08320": "Cumberland", "08321": "Cumberland", "08323": "Cumberland",
    "08324": "Cumberland", "08327": "Cumberland", "08329": "Cumberland",
    "08332": "Cumberland", "08345": "Cumberland", "08348": "Cumberland",
    "08349": "Cumberland", "08352": "Cumberland", "08353": "Cumberland",
    "08360": "Cumberland", "08361": "Cumberland",
    # Ocean
    "08005": "Ocean", "08006": "Ocean", "08008": "Ocean", "08050": "Ocean",
    "08087": "Ocean", "08092": "Ocean",
    "08527": "Ocean", "08533": "Ocean",
    "08701": "Ocean", "08721": "Ocean", "08722": "Ocean", "08723": "Ocean",
    "08724": "Ocean", "08731": "Ocean", "08732": "Ocean", "08733": "Ocean",
    "08734": "Ocean", "08735": "Ocean", "08738": "Ocean", "08740": "Ocean",
    "08741": "Ocean", "08742": "Ocean", "08751": "Ocean", "08752": "Ocean",
    "08753": "Ocean", "08755": "Ocean", "08757": "Ocean", "08758": "Ocean",
    "08759": "Ocean",
    # Monmouth (08xxx)
    "08501": "Monmouth", "08510": "Monmouth", "08514": "Monmouth",
    "08535": "Monmouth", "08555": "Monmouth",
    "08610": "Monmouth", "08611": "Monmouth",
    "08720": "Monmouth", "08730": "Monmouth", "08736": "Monmouth",
    "08750": "Monmouth",
    # Mercer
    "08520": "Mercer", "08525": "Mercer", "08534": "Mercer", "08536": "Mercer",
    "08540": "Mercer", "08542": "Mercer", "08544": "Mercer", "08550": "Mercer",
    "08560": "Mercer", "08561": "Mercer",
    "08608": "Mercer", "08609": "Mercer", "08618": "Mercer", "08619": "Mercer",
    "08620": "Mercer", "08628": "Mercer", "08629": "Mercer", "08638": "Mercer",
    "08648": "Mercer", "08690": "Mercer", "08691": "Mercer",
    # Middlesex (08xxx)
    "08512": "Middlesex", "08528": "Middlesex",
    "08810": "Middlesex", "08812": "Middlesex", "08816": "Middlesex",
    "08817": "Middlesex", "08820": "Middlesex", "08824": "Middlesex",
    "08828": "Middlesex", "08830": "Middlesex", "08831": "Middlesex",
    "08832": "Middlesex", "08837": "Middlesex", "08840": "Middlesex",
    "08846": "Middlesex", "08850": "Middlesex", "08852": "Middlesex",
    "08854": "Middlesex", "08857": "Middlesex", "08859": "Middlesex",
    "08861": "Middlesex", "08863": "Middlesex", "08872": "Middlesex",
    "08879": "Middlesex", "08882": "Middlesex", "08884": "Middlesex",
    "08901": "Middlesex", "08902": "Middlesex", "08904": "Middlesex",
    # Somerset (08xxx)
    "08502": "Somerset", "08553": "Somerset", "08558": "Somerset",
    "08805": "Somerset", "08807": "Somerset", "08821": "Somerset",
    "08823": "Somerset", "08835": "Somerset", "08836": "Somerset",
    "08844": "Somerset", "08853": "Somerset", "08869": "Somerset",
    "08873": "Somerset", "08876": "Somerset", "08880": "Somerset",
    "08890": "Somerset",
    # Hunterdon (08xxx)
    "08530": "Hunterdon", "08551": "Hunterdon", "08559": "Hunterdon",
    "08801": "Hunterdon", "08804": "Hunterdon", "08809": "Hunterdon",
    "08822": "Hunterdon", "08825": "Hunterdon", "08826": "Hunterdon",
    "08827": "Hunterdon", "08829": "Hunterdon", "08833": "Hunterdon",
    "08848": "Hunterdon", "08858": "Hunterdon", "08867": "Hunterdon",
    "08887": "Hunterdon", "08889": "Hunterdon",
    # Warren (08xxx)
    "08802": "Warren", "08865": "Warren", "08886": "Warren",
}

def get_county_for_zip(zip_code):
    """Return county name for a given 5-digit ZIP code."""
    zip_str = str(int(zip_code)).zfill(5)
    return NJ_ZIP_COUNTY.get(zip_str)

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
