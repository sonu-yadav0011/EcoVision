from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageChops, ImageEnhance, UnidentifiedImageError

from process_satellite import analyze_image, load_feature_extractor

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("ECOVISSION_DB_PATH", BASE_DIR / "data" / "ecovission.db"))
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(
    title="ECOVISSION API",
    description="Backend API for ECOVISSION forest-image screening prototype.",
    version="0.1.0",
)

origins = os.getenv(
    "ECOVISSION_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_model = None


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                image_name TEXT NOT NULL,
                image_width INTEGER NOT NULL,
                image_height INTEGER NOT NULL,
                total_tiles INTEGER NOT NULL,
                valid_tiles INTEGER NOT NULL,
                no_data_tiles INTEGER NOT NULL,
                category_counts_json TEXT NOT NULL,
                method TEXT NOT NULL
            )
        """)
        # Keep the existing Streamlit comparison-history schema compatible.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comparison_history (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                monitoring_area TEXT NOT NULL,
                earlier_image TEXT,
                later_image TEXT,
                earlier_label TEXT,
                later_label TEXT,
                flagged_pixels_pct REAL,
                flagged_pixels INTEGER,
                total_pixels INTEGER,
                sensitivity INTEGER,
                image_width INTEGER,
                image_height INTEGER
            )
        """)
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_model():
    global _model
    if _model is None:
        try:
            _model = load_feature_extractor()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The ResNet50V2 feature extractor could not be loaded. "
                    "Check that backend/models/res_net_model.keras contains "
                    "config.json and model.weights.h5, and that TensorFlow is installed. "
                    f"Details: {exc}"
                ),
            ) from exc
    return _model


async def read_upload(upload: UploadFile) -> Image.Image:
    if upload.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Upload a JPEG, PNG, or WebP image.",
        )
    raw = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 20 MB limit.")
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="The file is not a valid image.") from exc


def image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def report_records(report) -> list[dict[str, Any]]:
    records = report.replace({np.nan: None}).to_dict(orient="records")
    # Convert NumPy scalar values to native JSON values.
    return [
        {key: (value.item() if isinstance(value, np.generic) else value)
         for key, value in row.items()}
        for row in records
    ]


@app.get("/")
def root():
    return {"name": "ECOVISSION API", "status": "running", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database": str(DB_PATH),
        "model_loaded": _model is not None,
        "model_role": "ResNet50V2 feature extractor; forest labels remain RGB heuristics",
    }


@app.post("/api/analyze/single")
async def analyze_single(file: UploadFile = File(...)):
    image = await read_upload(file)
    model = get_model()
    try:
        result = analyze_image(image, model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {exc}") from exc

    report = result["report"]
    category_counts = {
        str(name): int(count)
        for name, count in report["category"].value_counts().items()
    }
    analysis_id = str(uuid.uuid4())
    created_at = now_iso()
    with connect_db() as conn:
        conn.execute(
            """INSERT INTO analyses
            (id, created_at, image_name, image_width, image_height,
             total_tiles, valid_tiles, no_data_tiles, category_counts_json, method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis_id, created_at, file.filename or "uploaded-image",
                result["image_width"], result["image_height"], result["total_tiles"],
                result["valid_tiles"], result["no_data_tiles"],
                json.dumps(category_counts),
                "RGB heuristic screening + ResNet50V2 feature embeddings",
            ),
        )
        conn.commit()

    return {
        "id": analysis_id,
        "created_at": created_at,
        "image": {
            "name": file.filename or "uploaded-image",
            "width": result["image_width"],
            "height": result["image_height"],
        },
        "summary": {
            "total_tiles": result["total_tiles"],
            "valid_tiles": result["valid_tiles"],
            "no_data_tiles": result["no_data_tiles"],
            "category_counts": category_counts,
        },
        "method": {
            "feature_extractor": "ResNet50V2 (2048-dimensional embeddings)",
            "category_assignment": "RGB heuristic rules; not a trained classifier",
        },
        "overlay_data_url": image_to_data_url(result["overlay"]),
        "tile_report": report_records(report),
    }


@app.post("/api/analyze/compare")
async def analyze_compare(
    earlier_file: UploadFile = File(...),
    later_file: UploadFile = File(...),
    monitoring_area: str = Form("Unspecified area"),
    earlier_label: str = Form("Earlier"),
    later_label: str = Form("Later"),
    sensitivity: int = Form(35),
):
    if not 1 <= sensitivity <= 255:
        raise HTTPException(status_code=422, detail="Sensitivity must be between 1 and 255.")
    earlier = await read_upload(earlier_file)
    later = await read_upload(later_file)
    if earlier.size != later.size:
        later = later.resize(earlier.size, Image.Resampling.LANCZOS)

    arr_a = np.asarray(earlier, dtype=np.int16)
    arr_b = np.asarray(later, dtype=np.int16)
    difference = np.mean(np.abs(arr_a - arr_b), axis=2)
    mask = difference >= sensitivity
    flagged_pixels = int(mask.sum())
    total_pixels = int(mask.size)
    flagged_pct = float(mask.mean() * 100.0)

    base = np.asarray(later).copy()
    red = np.zeros_like(base)
    red[:, :, 0] = 255
    base[mask] = (0.35 * base[mask] + 0.65 * red[mask]).astype(np.uint8)
    overlay = Image.fromarray(base)

    diff_img = ImageEnhance.Contrast(
        ImageChops.difference(earlier, later)
    ).enhance(2.0)

    comparison_id = str(uuid.uuid4())
    created_at = now_iso()
    with connect_db() as conn:
        conn.execute(
            """INSERT INTO comparison_history
            (id, created_at, monitoring_area, earlier_image, later_image,
             earlier_label, later_label, flagged_pixels_pct, flagged_pixels,
             total_pixels, sensitivity, image_width, image_height)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                comparison_id, created_at, monitoring_area.strip() or "Unspecified area",
                earlier_file.filename, later_file.filename, earlier_label, later_label,
                flagged_pct, flagged_pixels, total_pixels, sensitivity,
                earlier.width, earlier.height,
            ),
        )
        conn.commit()

    return {
        "id": comparison_id,
        "created_at": created_at,
        "monitoring_area": monitoring_area,
        "dimensions": {"width": earlier.width, "height": earlier.height},
        "sensitivity": sensitivity,
        "summary": {
            "flagged_pixels_pct": round(flagged_pct, 3),
            "flagged_pixels": flagged_pixels,
            "total_pixels": total_pixels,
        },
        "overlay_data_url": image_to_data_url(overlay),
        "difference_data_url": image_to_data_url(diff_img),
        "method": "RGB pixel-difference threshold; not validated forest-change detection",
    }


@app.get("/api/analyses")
def list_analyses(limit: int = 50):
    limit = max(1, min(limit, 200))
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["category_counts"] = json.loads(item.pop("category_counts_json"))
        output.append(item)
    return {"items": output, "count": len(output)}


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str):
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    item = dict(row)
    item["category_counts"] = json.loads(item.pop("category_counts_json"))
    return item


@app.get("/api/comparisons")
def list_comparisons(limit: int = 50):
    limit = max(1, min(limit, 200))
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT * FROM comparison_history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}
