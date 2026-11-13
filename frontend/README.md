# ECOVISSION React Frontend

Frontend-first React prototype with three pages: Main Dashboard (Nagaland map), Single Image Analysis (browser-side RGB tile heuristic), and Two Image Comparison (browser-side RGB pixel difference).

## Run
Requires Node.js 18+.
```bash
npm install
npm run dev
```
Open the Vite URL (usually http://localhost:5173). For production build: `npm run build`.

## Scope and limitations
- This is frontend-only; it does not connect to Python, FastAPI, SQLite or ResNet50V2.
- Single-image labels are basic RGB heuristics, not validated land-cover classification.
- RGB difference is not proof of forest loss.
- Map markers are approximate town centres, not forest-cover observations or hotspots.
- No NDVI, area or carbon estimates are calculated.
- Map tiles require internet access.
- Existing Streamlit and Python files are unchanged.
