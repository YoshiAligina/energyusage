"""
Validate the modeled per-ZIP bills (ui/nj_zip_info.json) against the
Census/ACS-derived ground-truth bills (data/raw/census_acs_electricity_bills.csv).

Aggregates our monthly modeled bills to an annual mean per ZIP, merges with the
census ZIP-year bills on the overlapping years, and reports fit diagnostics
(Pearson/Spearman correlation, bias, MAE, MAPE) pooled, per year, and per
utility. Writes the merged per-row table to
data/outputs/nj_modeled_vs_census.csv for inspection.

Run (from anywhere):
    python pipeline/06_validate_vs_census.py
"""

import json
from pathlib import Path

import pandas as pd

ROOT        = Path(__file__).resolve().parent.parent
UI_JSON     = ROOT / "ui" / "nj_zip_info.json"
CENSUS_CSV  = ROOT / "data" / "raw" / "census_acs_electricity_bills.csv"
OUT_CSV     = ROOT / "data" / "outputs" / "nj_modeled_vs_census.csv"


def load_modeled() -> pd.DataFrame:
    """Annual-mean modeled bill per ZIP from the UI JSON."""
    d = json.loads(UI_JSON.read_text(encoding="utf-8"))
    rows = []
    for z, p in d.items():
        mb = p.get("monthly_modeled_bill") or {}
        if not mb:
            continue
        s = pd.Series(mb)
        s.index = pd.to_datetime(s.index, format="%Y-%m")
        for yr, val in s.groupby(s.index.year).mean().items():
            rows.append({"YEAR": int(yr), "ZIP_Code": z,
                         "modeled_bill": float(val),
                         "utility": p.get("utility_name")})
    return pd.DataFrame(rows)


def load_census() -> pd.DataFrame:
    cen = pd.read_csv(CENSUS_CSV, dtype={"ZIP_Code": str, "YEAR": int})
    cen["ZIP_Code"] = cen["ZIP_Code"].str.zfill(5)
    cen["census_bill"] = (cen["Avg_Monthly_Electricity_Bill"]
                            .str.replace("$", "", regex=False)
                            .str.replace(",", "")
                            .astype(float))
    return cen[["YEAR", "ZIP_Code", "census_bill"]]


def report(m: pd.DataFrame) -> None:
    def block(g):
        pr = g[["modeled_bill", "census_bill"]].corr(method="pearson").iloc[0, 1]
        sp = g[["modeled_bill", "census_bill"]].corr(method="spearman").iloc[0, 1]
        err = g["modeled_bill"] - g["census_bill"]
        mape = (err / g["census_bill"] * 100).abs().mean()
        return pr, sp, err.mean(), err.abs().mean(), mape

    pr, sp, bias, mae, mape = block(m)
    print(f"\n=== POOLED ({sorted(m.YEAR.unique())}) ===")
    print(f"  n={len(m)}  Pearson={pr:.4f}  Spearman={sp:.4f}")
    print(f"  mean modeled=${m.modeled_bill.mean():.2f}  "
          f"mean census=${m.census_bill.mean():.2f}")
    print(f"  bias=${bias:+.2f}  MAE=${mae:.2f}  MAPE={mape:.1f}%")

    print("\n=== PER YEAR ===")
    for yr, g in m.groupby("YEAR"):
        pr, _, bias, _, _ = block(g)
        print(f"  {yr}: n={len(g):3d}  Pearson={pr:.3f}  "
              f"modeled=${g.modeled_bill.mean():.2f}  "
              f"census=${g.census_bill.mean():.2f}  bias=${bias:+.2f}")

    print("\n=== PER UTILITY ===")
    for u, g in m.groupby("utility"):
        if g.utility.iloc[0] is None:
            continue
        pr, _, bias, _, _ = block(g)
        print(f"  {u:25s}: n={len(g):4d}  r={pr:.3f}  "
              f"modeled=${g.modeled_bill.mean():.2f}  "
              f"census=${g.census_bill.mean():.2f}  bias=${bias:+.2f}")


def main() -> None:
    mod = load_modeled()
    cen = load_census()
    m = mod.merge(cen, on=["YEAR", "ZIP_Code"], how="inner")
    if m.empty:
        print("No overlapping ZIP-years between modeled and census data.")
        return
    report(m)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    m.sort_values(["YEAR", "ZIP_Code"]).to_csv(OUT_CSV, index=False,
                                               float_format="%.2f")
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
