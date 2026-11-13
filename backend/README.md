# ECOVISSION Backend — Phase 1

## What this provides
- FastAPI backend for the existing React/Vite frontend.
- Single-image screening endpoint using the existing `process_satellite.py`.
- Two-image RGB-difference endpoint.
- SQLite persistence for single analyses and comparisons.
- CORS configured for the Vite development server.

## Important model note
The supplied `process_satellite.py` uses ResNet50V2 to create 2,048-dimensional feature embeddings. The forest category labels are still assigned by RGB heuristic rules. This is **not** a trained forest-condition classifier.

The uploaded `config.json` and `metadata.json` describe the Keras model, but the required `model.weights.h5` file was not included in the uploaded files. Put the complete model directory here:

`backend/models/res_net_model.keras/config.json`  
`backend/models/res_net_model.keras/metadata.json`  
`backend/models/res_net_model.keras/model.weights.h5`

Do not run model inference until the weights file is present.

## Setup (Windows PowerShell)
From this backend folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy the complete `res_net_model.keras` model directory into `backend/models/`.

Start the API:

```powershell
uvicorn main:app --reload
```

Open:
- API health: http://127.0.0.1:8000/api/health
- Interactive API docs: http://127.0.0.1:8000/docs

## Endpoints
- `GET /api/health`
- `POST /api/analyze/single` — multipart field `file`
- `POST /api/analyze/compare` — multipart fields `earlier_file`, `later_file`; optional form fields `monitoring_area`, `earlier_label`, `later_label`, `sensitivity`
- `GET /api/analyses`
- `GET /api/analyses/{analysis_id}`
- `GET /api/comparisons`

SQLite database is created automatically at `data/ecovission.db`.

## Current limitations
- Comparison is RGB pixel difference only; images are resized to the earlier image dimensions but not geographically registered.
- Single-image categories are RGB heuristic screening, not validated land-cover predictions.
- Geospatial area estimates, satellite catalogue integration, and trained classifier inference are not included in Phase 1.
