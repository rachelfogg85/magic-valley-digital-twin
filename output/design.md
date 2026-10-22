# Magic Valley Digital Twin — Design

`web/` — a single-page three.js app (no build step, ES modules via an import map), served by `server/app.py` (Flask) at `http://localhost:5050`.

**Note on color:** this started as a white background with forest green headers (the project's chosen house style, replacing the MGT 409 folder's default black-and-pink). After seeing it, you said the green header text didn't work against white, so green was pulled back to an accent only — a thin underline under the title and the slider handles — with all headings and body text in plain dark neutral color instead. The section below describes that final version; the iteration log at the bottom records the pivot.

## The concept: a map you can scrub through time

The core idea is a 3D terrain of a real ~5,700-acre patch of Magic Valley, Idaho (near Jerome), textured with the actual crop grown in every field, every year from 2008–2021. Dragging the year slider replays real planting history — you can watch a field rotate from alfalfa to wheat to potatoes over the years, or sit fallow in a drought year. The vertical exaggeration slider is there because real Magic Valley terrain is subtle (about 70 vertical meters across the whole box); without exaggeration, the land looks almost flat and the Snake River Plain's gentle topography is easy to miss.

## Color system: white background, forest green as an accent only

- **Background:** white, everywhere — the 3D scene's clear color, the control panel, and (per `CLAUDE.md`) the report and any future agent chat UI.
- **Text:** dark neutral (`--ink`, near-black) for all headings and body copy. Not green — green text on a white background was tried first and read as clashing once actually seen on screen.
- **Forest green (`--forest`, `#1E5631`):** used sparingly, only as a non-text accent — a 3px underline beneath the panel title, and the `accent-color` on the two range sliders (so the slider track/handle reads green without a single word of text being green).
- **Font:** Arial/Helvetica, matching the "clean and simple, audience has never seen this before" brief — no decorative or technical-looking fonts.
- **Legend section label** ("What's growing here") is small, uppercase, letter-spaced, and gray — a quiet section header rather than competing with the main title.

## Crop names: plain language over GIS jargon

The USDA Cropland Data Layer's official class names are dataset jargon in places — "Developed/High Intensity," "Dbl Crop WinWht/Corn," "Herbaceous Wetlands." Since the audience is "a smart manager who has never seen the app," `pipeline/cdl_layman_names.py` maps each of these to a plain term shown in the UI (e.g. "City / Dense Buildings," "Wheat then Corn (double crop)," "Wetland (marsh)"). The official USDA name is kept alongside it in the data (`cdl_legend.json`'s `official_name` field, shown as a hover tooltip) so the report can still cite the authoritative source.

## Making the crop map look clean, not like raw pixels

Raw CDL data is genuinely noisy at the pixel level — real classification error shows up as scattered single-pixel flecks of an unlikely crop inside a larger field. Once the 3D viewer was actually looking clean in a screenshot but still read as "pixelly" in your own browser, three things fixed it (`pipeline/03_process_rasters.py`):

1. **Sieve filter** (`rasterio.features.sieve`, threshold 16 px) merges any contiguous patch smaller than one native 30 m CDL cell's footprint into its larger neighbor, before any color is applied.
2. **2x upsample + light Gaussian blur** on the final PNG softens the remaining hard pixel grid into smoother field edges. This is cosmetic only — field boundaries, crop codes, and the zonal-majority crop history are all computed from the un-blurred classified raster, never from this display image.
3. **Linear/mipmap texture filtering** in three.js (`web/terrain.js`), replacing an initial nearest-neighbor choice that had been crisp but visibly blocky up close.

## Layout

A single floating white panel, top-left, over the full-bleed 3D canvas:

1. **Title** ("Magic Valley Digital Twin") with the green underline accent.
2. **Year slider** (2008–2021) — swaps the crop texture only, instant, no reload.
3. **Vertical exaggeration slider** (1x–10x, default 4x) — recomputes terrain height in place.
4. **Legend** ("What's growing here") — scrollable list of every crop present in the study area, color swatch + plain name, official USDA name on hover.
5. **Disclaimer** — "Decision aid, not farm advice," required by the project's own rules, always visible, never hidden behind a scroll.

## Design iteration log

Real, requested changes, in order:

1. **Initial build:** white background, forest green headers and section titles, Arial font.
2. **"The green and white box" / "green for the words" — removed:** green text on white, seen in the running app, didn't read well. Reworked so green is a thin underline + slider accent only, with all text switched to dark neutral.
3. **"Crop names need to be in more layman's terms":** added `cdl_layman_names.py` to translate official USDA class names to plain English in the legend, keeping the official name as a hover tooltip for traceability.
4. **"The image still looks pixelly" (asked twice, after an initial noise-filter pass wasn't enough):** escalated from a sieve-only cleanup to sieve + 2x upsample + Gaussian blur on the display PNG, plus switching the three.js texture from nearest to linear/mipmap filtering.

## Running it

```bash
cd "Final Project"
source venv/bin/activate
python server/app.py
```

Opens on `http://localhost:5050` (port 5000 is avoided — macOS's AirPlay Receiver squats on it by default).
