from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from PIL import Image
from tensorflow.keras.applications.resnet_v2 import preprocess_input

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "res_net_model.keras"
PACKED_MODEL = BASE_DIR / "models" / ".packed_resnet50v2.keras"

CLASS_NAMES = {
    0: "Intact Forest",
    1: "Degraded / Jhum Scrub",
    2: "Deforested / Cleared Land",
    3: "No Data",
}

COLORS = {
    0: (34, 139, 34),
    1: (255, 193, 7),
    2: (220, 53, 69),
    3: (125, 135, 140),
}

PATCH_SIZE = 160
# A tile is flagged as possible No Data only when at least this share
# of pixels are almost black. This is a practical JPEG screening rule,
# not a guaranteed satellite-data validity mask.
BLACK_PIXEL_THRESHOLD = 12
NO_DATA_TILE_RATIO = 0.60


def prepare_model_archive():
    if not MODEL_DIR.exists():
        raise FileNotFoundError(f"Model directory not found: {MODEL_DIR}")
    if not (MODEL_DIR / "config.json").exists():
        raise FileNotFoundError("Missing config.json")
    if not (MODEL_DIR / "model.weights.h5").exists():
        raise FileNotFoundError("Missing model.weights.h5")

    if not PACKED_MODEL.exists():
        with zipfile.ZipFile(PACKED_MODEL, "w") as archive:
            for file in MODEL_DIR.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(MODEL_DIR))
    return PACKED_MODEL


def load_feature_extractor():
    archive = prepare_model_archive()
    model = tf.keras.models.load_model(
        archive, compile=False, safe_mode=True
    )
    if model.input_shape[1:] != (160, 160, 3):
        raise ValueError(f"Unexpected model input shape: {model.input_shape}")
    if model.output_shape[-1] != 2048:
        raise ValueError(f"Expected 2048 features, got {model.output_shape}")
    return model


def load_image(image):
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    if not isinstance(image, Image.Image):
        raise TypeError("Input must be a PIL image or file path.")
    return image.convert("RGB")


def extract_patches(image, patch_size=PATCH_SIZE):
    image = load_image(image)
    width, height = image.size
    patches, coordinates = [], []

    # Only complete tiles are used. Any remainder at the right/bottom
    # edges is currently omitted and is not counted in the report.
    for y in range(0, height - patch_size + 1, patch_size):
        for x in range(0, width - patch_size + 1, patch_size):
            patch = image.crop((x, y, x + patch_size, y + patch_size))
            patches.append(np.asarray(patch))
            coordinates.append((x, y))
    return patches, coordinates


def calculate_indices(patch):
    """Calculate RGB-only vegetation screening features and black-pixel share."""
    image = np.asarray(patch, dtype=np.float32)
    image_01 = image / 255.0

    red = image_01[:, :, 0]
    green = image_01[:, :, 1]
    blue = image_01[:, :, 2]

    exg = 2 * green - red - blue
    exg_score = float(np.clip((exg.mean() + 1.0) / 3.0, 0, 1))

    brightness = (red + green + blue) / 3.0
    canopy_ratio = float(np.mean(
        (green > red * 1.05)
        & (green > blue * 1.05)
        & (brightness > 0.12)
    ))

    # Treat near-black pixels as possible missing/blank image pixels.
    black_pixels = np.all(image <= BLACK_PIXEL_THRESHOLD, axis=2)
    no_data_ratio = float(black_pixels.mean())

    return exg_score, canopy_ratio, no_data_ratio


def calculate_risk(exg_score, canopy_ratio):
    vegetation_score = 0.45 * exg_score + 0.55 * canopy_ratio
    risk_score = 1.0 - vegetation_score

    if vegetation_score >= 0.60:
        category = 0
    elif vegetation_score >= 0.35:
        category = 1
    else:
        category = 2
    return float(risk_score), category


def extract_embeddings(model, patches, batch_size=32):
    if not patches:
        return np.empty((0, 2048), dtype=np.float32)
    images = np.asarray(patches, dtype=np.float32)
    images = preprocess_input(images)
    return model.predict(images, batch_size=batch_size, verbose=0)


def create_risk_overlay(image, results, coordinates):
    image = load_image(image)
    overlay = np.asarray(image).copy()
    for result, (x, y) in zip(results, coordinates):
        color = COLORS[result["category_id"]]
        overlay[y:y + PATCH_SIZE, x:x + PATCH_SIZE] = color
    return Image.blend(image, Image.fromarray(overlay), alpha=0.35)


def analyze_image(image, model):
    """Run RGB screening. Categories are heuristic, not validated land cover."""
    image = load_image(image)
    patches, coordinates = extract_patches(image)
    if not patches:
        raise ValueError("Image must be at least 160 × 160 pixels.")

    embeddings = extract_embeddings(model, patches)
    results = []

    for index, (patch, embedding, coordinate) in enumerate(
        zip(patches, embeddings, coordinates)
    ):
        exg, canopy, no_data_ratio = calculate_indices(patch)

        if no_data_ratio >= NO_DATA_TILE_RATIO:
            category = 3
            risk_score = None
        else:
            risk_score, category = calculate_risk(exg, canopy)

        results.append({
            "tile_id": index + 1,
            "x": coordinate[0],
            "y": coordinate[1],
            "exg_score": round(exg, 4),
            "canopy_ratio": round(canopy, 4),
            "possible_no_data_ratio": round(no_data_ratio, 4),
            "risk_score": (
                round(risk_score, 4) if risk_score is not None else None
            ),
            "category_id": category,
            "category": CLASS_NAMES[category],
            "embedding_norm": float(np.linalg.norm(embedding)),
        })

    report = pd.DataFrame(results)
    overlay = create_risk_overlay(image, results, coordinates)

    return {
        "report": report,
        "overlay": overlay,
        "embeddings": embeddings,
        "total_tiles": len(results),
        "valid_tiles": int((report["category_id"] != 3).sum()),
        "no_data_tiles": int((report["category_id"] == 3).sum()),
        "image_width": image.width,
        "image_height": image.height,
    }
