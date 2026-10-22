# Magic Valley Digital Twin

A browser-based 3D twin of a few square miles of real Idaho farmland (Magic Valley, near Jerome, ID),
showing what was planted in every field since 2008 and recommending what to plant under a water
shortage using a linear-program optimizer and an AI agent.

Status: project scaffolded, data pipeline not yet run. See `CLAUDE.md` for the full design and
`../BUILD_PLAN.md` style step list for how this is being built incrementally.

## Run it (once the pipeline has been run — not yet true)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server/app.py
```

Open http://localhost:5050 (port 5000 is avoided since macOS's AirPlay Receiver often squats on it).
The year slider and scenario sliders work without any API key. The chat
box needs a `.env` file (copy `.env.example`) with `PORTKEY_API_KEY` set to use the in-app agent.

## Data

All data needed to run the app is pre-downloaded into `data/processed/` by the scripts in
`pipeline/`; no API keys are needed for data. See `config.yaml` for the study area and years.
