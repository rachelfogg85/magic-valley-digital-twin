# Magic Valley Digital Twin

A browser-based 3D twin of real Idaho farmland (~5,700 acres near Jerome, ID) showing what was
planted in every field since 2008, with a linear-program optimizer and an AI agent that recommend
what to plant under a water shortage. See [report/report.html](report/report.html) (open by
double-clicking, no server needed) for the full writeup, or [output/design.md](output/design.md)
for the visual design notes.

## Run it from a fresh clone

Requires Python 3.12 (newer Python releases may not have prebuilt `rasterio` wheels yet; see
`requirements.txt`'s pinned `rasterio==1.4.3` note if you hit a build error).

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server/app.py
```

Open **http://localhost:5050** (port 5000 is skipped on purpose — macOS's AirPlay Receiver often
squats on it). The year/exaggeration/"find a crop" sliders and the "Run plan" scenario tool work
immediately, with no API key. Only the chat box at the bottom needs a key — see below.

All data the app needs is already in `data/processed/` (committed to this repo); no data API keys
or re-running the pipeline is required to use the app. `data/raw/` (the original downloads) is
gitignored and not needed to run the app — only to regenerate `data/processed/` from scratch via
the numbered scripts in `pipeline/` (see `CLAUDE.md` for what each one does).

### Enabling the chat assistant

1. Copy `.env.example` to `.env` in this folder (or one folder above — the app checks both).
2. Set `PORTKEY_API_KEY` to the course-provided key (model `gpt-6-luna`), or `OPENAI_API_KEY` with
   your own OpenAI key and model, per the course's model rules.
3. Restart `python server/app.py`. If no key is found, the chat box hides itself automatically and
   shows a note that the sliders still work without it — this is expected, not a bug.

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
- `report/` — `report.html` (built by `report/build_report.py`, which embeds the figures) and
  `output/design.md` (visual design decisions and iteration history).

## Running the tests

```bash
source venv/bin/activate
pytest optimizer/
```

## Limitations

See the Limits and next steps section of `report/report.html` — field boundaries are
algorithmically generated (not hand-traced, since geojson.io was unavailable), and crop cost
figures are representative rather than exact University of Idaho enterprise-budget numbers.
