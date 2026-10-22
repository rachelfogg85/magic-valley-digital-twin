# Project: Magic Valley Digital Twin

## Goal
A browser-based 3D model of a few square miles of real Idaho farmland (Magic Valley).
- Terrain from USGS 3DEP elevation data.
- Every field colored by the USDA Cropland Data Layer (CDL), 2008 to latest year, with a year slider.
- A linear-program optimizer picks the crop for each field to maximize profit under a water limit
  and rotation rules.
- An AI agent (Portkey, model "gpt-6-luna", OpenAI-compatible tool use) turns plain-language scenarios
  into optimizer runs and explains the results. Fields recolor in 3D; a panel shows profit and water use.
- A backtest compares what farmers actually planted in a drought year (CDL) with the optimizer's
  plan, and reports the dollar gap.

## Tech stack
- Python 3.11+ for data processing, optimizer, backtest, and the local server.
  Libraries: rasterio, geopandas, shapely, numpy, pandas, Pillow, pulp, flask, openai, python-dotenv, pytest.
- Frontend: a single plain HTML/JS page using three.js (ES modules, vendored locally in web/vendor/),
  no build step, no framework.
- Optimizer: PuLP (CBC solver) in Python, the single source of truth used by the app AND the backtest.
- Agent: OpenAI Python SDK pointed at the Portkey gateway, model "gpt-6-luna", tool use.
  Key read from .env as PORTKEY_API_KEY. If a personal OpenAI key is ever substituted instead, it
  must be named OPENAI_API_KEY per course rules. Never use any other provider's key without first
  checking the course project rules (other keys require hosting the app online and instructor sign-off).

## Repo layout
config.yaml                 study-area bounding box, years, drought year, file paths
data/raw/                   original downloads (DEM GeoTIFF, CDL GeoTIFFs, CSVs, PDFs)
data/processed/             files the app loads: heightmap.bin, terrain_meta.json, cdl_YYYY.png,
                            fields.geojson, field_history.csv, crop_params.csv, water_baseline.csv
pipeline/                   numbered Python scripts: 01_download_dem.py, 02_download_cdl.py, ...
optimizer/                  lp.py (solve function), test_lp.py
agent/                      agent.py (tool definitions, system prompt, loop)
server/app.py               Flask: serves web/, POST /api/optimize, POST /api/agent
web/                        index.html, main.js, terrain.js, fields.js, panel.js, chat.js, vendor/
backtest/                   run_backtest.py, outputs/
report/                     report.html (final deliverable), figures/

## Visual style (web/, report/, and any agent chat UI)
- White background, Arial/Helvetica font, dark neutral text (not green) for all
  headings and body copy. Forest green (#1E5631) is reserved for a single thin
  underline accent under the main title -- NOT text color, and NOT slider/control
  colors either (tried both, asked to remove both times). Sliders and other controls
  use neutral gray (#555) instead.
- Clean and simple: the audience is a smart manager/farmer who has never seen the app,
  not a GIS specialist, so prefer plain language and minimal clutter over dense detail.

## Rules (always follow)
1. Every number shown to the user comes from the data files or the optimizer, never from the
   language model. The agent may only state numbers that appear in a tool result.
2. Profit is shown as an estimate with a low / mid / high range, never a single certain number.
3. The UI says it is a decision aid, not farm advice.
4. All data is pre-downloaded into data/. The app must run with no data API keys.
5. The app must also run WITHOUT a Portkey/OpenAI API key: scenario sliders call /api/optimize
   directly; only the chat box needs the key.
6. Keep code simple and commented; this is a short student project, not production.
7. After changing code, run the relevant tests or script and show me the output.
8. Course deliverable rules (from the project requirements page): a public (or shared-with-zlisto)
   GitHub repo, a README.md with run instructions, a .env.example listing required key names with
   no real values, and the app must look for .env in its own folder first, then one level up. Never
   commit a real .env or the PORTKEY_API_KEY value anywhere (code, logs, docs, screenshots).
