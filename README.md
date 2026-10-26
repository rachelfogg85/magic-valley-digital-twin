# Magic Valley Digital Twin

A browser-based 3D twin of real Idaho farmland (102 fields, ~4,993 acres near Jerome, ID) showing
what was planted in every field since 2008, with a linear-program optimizer and an AI agent that
recommend what to plant under a water shortage. See [report/report.html](report/report.html) (open
by double-clicking, no server needed) for the full writeup, or [output/design.md](output/design.md)
for the visual design notes.

## Run it from a fresh clone

Needs Python 3.11 or newer (3.14 is fine). Four commands:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server/app.py
```

Open **http://localhost:5050** (port 5000 is skipped on purpose — macOS's AirPlay Receiver often
squats on it). Everything except the chat assistant works immediately with no API key — only the
"Ask the Farmer" box at the top needs one (see "Enabling the chat assistant" below).

All data the app needs is already in `data/processed/` (committed to this repo); no data API keys
or re-running the pipeline is required to use the app. `data/raw/` (the original downloads) is
gitignored and not needed to run the app.

<details>
<summary><strong>Only if you want to regenerate the data from scratch</strong></summary>

The numbered scripts in `pipeline/` rebuild `data/processed/` from the original public sources
(see `CLAUDE.md` for what each one does). They need extra geo-raster libraries, which the app
itself does not:

```bash
pip install -r requirements-pipeline.txt
```

That pulls in `rasterio==1.4.3`, which has no prebuilt wheel for Python 3.14+ (pip would try to
build it from source, which needs GDAL). So use **Python 3.11–3.13** for the pipeline. If your
`python3` is newer, [`uv`](https://docs.astral.sh/uv/) gets you a compatible one without touching
your system install:

```bash
uv venv --python 3.12 venv-pipeline
source venv-pipeline/bin/activate
uv pip install -r requirements-pipeline.txt
```
</details>

### Enabling the chat assistant

1. Copy `.env.example` to `.env` in this folder (or one folder above — the app checks both).
2. Set `PORTKEY_API_KEY` to the course-provided key (model `gpt-6-luna`), or `OPENAI_API_KEY` with
   your own OpenAI key and model, per the course's model rules.
3. Restart `python server/app.py`. If no key is found, the chat box hides itself automatically and
   shows a note that the sliders still work without it — this is expected, not a bug.

## Using the app

The screen has three parts: the **map** in the middle, the **Land & Crop Key** on the left, and the
**Land and Water Optimizer** on the right, with the **Ask the Farmer** chat box at the top.

**1. Explore the land (left panel).** Drag to orbit the 3D terrain, scroll to zoom, and hover any
field to see its size and what was actually planted there that year. Move the **Year** slider
(2008–2021) to replay two decades of real USDA crop history — the fields recolor each year.
**Vertical exaggeration** stretches the terrain so the canyon and slopes are easier to read, and
**Find a crop** highlights every field growing one crop so you can see how it moved around over
time.

**2. Run a water scenario (right panel).** This is the core of the tool:

- Set **Water available** (30%–120% of a normal year; 100% = 11,780 acre-feet, the long-run average
  delivery here, and 2021's real drought cut it to about 67%).
- Pick a **Price outlook** — Worst / Base / Optimal Case, based on the real 2018–2022 spread in
  Idaho crop prices.
- Click **Run plan**. The optimizer assigns a crop to each of the 102 fields to maximize profit
  under that water limit, the real rotation rules, and the sugar beet / potato contract caps.

The map recolors to show the recommended plan, and the panel reports the estimated profit range,
how much of the water budget the plan uses, acres by crop, and — for comparison — what was actually
planted that year. Expand **How profit is calculated** to see every price, yield, and cost figure
with its source.

**3. Ask in plain English (chat box).** With a key configured, ask things like *"We have 30% less
water this year, what should I plant?"* or *"What has field F10 grown historically?"* The assistant
runs the same optimizer behind the scenes, so the sliders and results panel update to match its
answer, and it reports its own token usage under each reply. It only states numbers that came back
from a tool call — if you ask it to confirm a number it can't verify, it will refuse.

> This is a decision aid, not farm advice. Profit is always shown as a range, never a single
> certain number.

## Repo layout

- `pipeline/` — numbered scripts that build `data/processed/` from public sources (USGS terrain,
  USDA crop data, Idaho price/yield data). Not needed to run the app, only to regenerate its data.
- `optimizer/lp.py` — the linear program (PuLP); `optimizer/test_lp.py` has hand-checkable tests
  (`pytest optimizer/`).
- `agent/` — the chat agent (`agent.py`) and the tool functions it shares with the Flask API
  (`tools.py`), so the map and the chat agent always compute the same plan.
- `server/app.py` — Flask: serves `web/`, `data/processed/`, `POST /api/optimize`, `POST /api/agent`.
- `web/` — the 3D viewer (plain JS + three.js, no build step, no framework).
- `backtest/run_backtest.py` — the 2021 drought-year backtest; `backtest/outputs/` has its charts
  and CSV.
- `report/` — `report.html` and `slides.html`, each built as a single self-contained file by
  `build_report.py` / `build_slides.py` (they embed everything in `report/figures/`).
- `output/design.md` — visual design decisions and iteration history.

## Running the tests

```bash
source venv/bin/activate
pytest optimizer/
```

## Limitations

See the Limits and next steps section of `report/report.html` — field boundaries are
algorithmically generated (not hand-traced, since geojson.io was unavailable), and crop cost
figures are representative rather than exact University of Idaho enterprise-budget numbers.
