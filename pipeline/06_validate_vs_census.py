"""
Validate the modeled per-ZIP bills (ui/nj_zip_info.json) against the
Census/ACS-derived ground-truth bills (data/raw/census_acs_electricity_bills.csv).

The calibration multiplier baked into the modeled bills is fit by
05_build_ui_json.py on the pooled TRAIN years (2021-2023) via OLS-through-origin.
This script evaluates that choice with a temporal split:

    TRAIN      2021-2023  — in-sample fit, pooled (all overlap years up to 2024)
    VALIDATE   2024        — out-of-sample fit (the honest test of the multiplier)
    PREDICT    2025, 2026  — modeled bills exist (EIA has these months) but the
                             census has not released them, so these are genuine
                             forward predictions with no ground truth yet.

The headline metric is the correlation coefficient (Pearson r) — does the model
rank/track ZIP bills correctly — supported by Spearman, bias, MAE, and MAPE. The
merged per-row table is written to data/outputs/nj_modeled_vs_census.csv.

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

TRAIN_YEARS    = (2021, 2022, 2023)   # pooled training (all overlap years up to 2024)
VALIDATE_YEAR  = 2024                  # held-out, out-of-sample
PREDICT_YEARS  = (2025, 2026)          # no census ground truth yet


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


def fit_stats(g: pd.DataFrame) -> dict:
    """Correlation + error metrics for one modeled-vs-census slice."""
    pr = g[["modeled_bill", "census_bill"]].corr(method="pearson").iloc[0, 1]
    sp = g[["modeled_bill", "census_bill"]].corr(method="spearman").iloc[0, 1]
    err = g["modeled_bill"] - g["census_bill"]
    return {
        "n": len(g),
        "pearson": pr,
        "spearman": sp,
        "bias": err.mean(),
        "mae": err.abs().mean(),
        "mape": (err / g["census_bill"] * 100).abs().mean(),
        "mean_modeled": g["modeled_bill"].mean(),
        "mean_census": g["census_bill"].mean(),
    }


def print_block(title: str, g: pd.DataFrame) -> None:
    s = fit_stats(g)
    print(f"\n--- {title} ---")
    print(f"  n={s['n']}   correlation coefficient (Pearson r) = {s['pearson']:.4f}"
          f"   Spearman = {s['spearman']:.4f}")
    print(f"  mean modeled = ${s['mean_modeled']:.2f}   "
          f"mean census = ${s['mean_census']:.2f}")
    print(f"  bias = ${s['bias']:+.2f}   MAE = ${s['mae']:.2f}   "
          f"MAPE = {s['mape']:.1f}%")


def main() -> None:
    mod = load_modeled()
    cen = load_census()
    m = mod.merge(cen, on=["YEAR", "ZIP_Code"], how="inner")
    if m.empty:
        print("No overlapping ZIP-years between modeled and census data.")
        return

    print("=" * 70)
    print(f"CALIBRATION VALIDATION  —  multiplier trained on {TRAIN_YEARS}, "
          f"validated on {VALIDATE_YEAR}")
    print("=" * 70)

    # TRAIN: pooled in-sample fit (multiplier was fit on these years).
    train_mask = m.YEAR.isin(TRAIN_YEARS)
    if train_mask.any():
        print_block(f"TRAIN  {TRAIN_YEARS}  pooled (in-sample)", m[train_mask])
        # also per training year, so drift across the training window is visible
        for yr in sorted(TRAIN_YEARS):
            if (m.YEAR == yr).any():
                print_block(f"  train year {yr}", m[m.YEAR == yr])

    # VALIDATE: out-of-sample — the honest test.
    if (m.YEAR == VALIDATE_YEAR).any():
        print_block(f"VALIDATE  {VALIDATE_YEAR}  (out-of-sample — the honest test)",
                    m[m.YEAR == VALIDATE_YEAR])

    # PREDICT: modeled bills exist but census does not yet — no ground truth.
    print(f"\n--- PREDICT  {PREDICT_YEARS}  (no census ground truth yet) ---")
    for yr in PREDICT_YEARS:
        g = mod[mod.YEAR == yr]
        if g.empty:
            print(f"  {yr}: no modeled data")
            continue
        print(f"  {yr}: n={len(g):3d}   mean modeled = ${g.modeled_bill.mean():.2f}"
              f"   (census unavailable — forward prediction)")

    # Per-utility breakdown on the validation year.
    print(f"\n--- PER UTILITY  (validation year {VALIDATE_YEAR}) ---")
    vy = m[m.YEAR == VALIDATE_YEAR]
    for u, g in vy.groupby("utility"):
        if g.utility.iloc[0] is None:
            continue
        s = fit_stats(g)
        print(f"  {u:25s}: n={s['n']:4d}  r={s['pearson']:.3f}  "
              f"modeled=${s['mean_modeled']:.2f}  census=${s['mean_census']:.2f}  "
              f"bias=${s['bias']:+.2f}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    m.sort_values(["YEAR", "ZIP_Code"]).to_csv(OUT_CSV, index=False,
                                               float_format="%.2f")
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
