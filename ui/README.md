# NJ ZIP UI Data Bridge

This UI reads `nj_zip_info.json`.

You can auto-generate that file from PJM trend outputs with:

```bash
python fetch_lmps.py --summary-only --build-ui-json --start-year 2020 --end-year 2025 --location-type LOAD
```

## Required mapping file

Fill `zip_to_pnode_map.csv` with real `pnode_id` values:

- `zip`: 5-digit ZIP code
- `pnode_id`: PJM node ID from `data/trend_load_2020_2025.csv`
- `county`: optional label shown in UI

If `pnode_id` values do not match the trend file, JSON generation will fail with a clear message.

## Full pipeline + UI JSON

```bash
python fetch_lmps.py --start-year 2020 --end-year 2025 --location-type LOAD --build-ui-json
```

This writes:

- `data/trend_load_2020_2025.csv`
- `ui/nj_zip_info.json`
