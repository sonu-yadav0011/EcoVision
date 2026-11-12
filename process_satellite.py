
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import tensorflow as tf

from PIL import Image
from tensorflow.keras.applications.resnet_v2 import preprocess_input


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "res_net_model.keras"
PACKED_MODEL = BASE_DIR / "models" / ".packed_resnet50v2.keras"

CLASS_NAMES = {
    0: "Intact Forest",
    1: "Degraded / Jhum Scrub",
    2: "Deforested / Cleared Land",
}

COLORS = {
    0: (34, 139, 34),      # Green
    1: (255, 193, 7),      # Yellow
    2: (220, 53, 69),      # Red
}

PATCH_SIZE = 160


# --------------------------------------------------
# MODEL LOADING
# --------------------------------------------------

def prepare_model_archive():
    """Package an extracted Keras model directory for Keras 3."""

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"Model directory not found: {MODEL_DIR}"
        )

    if not (MODEL_DIR / "config.json").exists():
        raise FileNotFoundError("Missing config.json")

    if not (MODEL_DIR / "model.weights.h5").exists():
        raise FileNotFoundError("Missing model.weights.h5")

    if not PACKED_MODEL.exists():
        with zipfile.ZipFile(PACKED_MODEL, "w") as archive:
            for file in MODEL_DIR.rglob("*"):
                if file.is_file():
                    archive.write(
                        file,
                        file.relative_to(MODEL_DIR)
                    )

    return PACKED_MODEL


def load_feature_extractor():
    """Load the existing ResNet50V2 feature extractor."""

    archive = prepare_model_archive()

    model = tf.keras.models.load_model(
        archive,
        compile=False,
        safe_mode=True
    )

    if model.input_shape[1:] != (160, 160, 3):
        raise ValueError(
            f"Unexpected model input shape: {model.input_shape}"
        )

    if model.output_shape[-1] != 2048:
        raise ValueError(
            f"Expected 2048 features, got {model.output_shape}"
        )

    return model


# --------------------------------------------------
# IMAGE PROCESSING
# --------------------------------------------------

def load_image(image):
    """Convert uploaded image or file path into RGB."""

    if isinstance(image, (str, Path)):
        image = Image.open(image)

    if not isinstance(image, Image.Image):
        raise TypeError("Input must be a PIL image or file path.")

    return image.convert("RGB")


def extract_patches(image, patch_size=PATCH_SIZE):
    """Split image into non-overlapping patches."""

    image = load_image(image)

    width, height = image.size

    patches = []
    coordinates = []

    for y in range(0, height - patch_size + 1, patch_size):
        for x in range(0, width - patch_size + 1, patch_size):

            patch = image.crop(
                (x, y, x + patch_size, y + patch_size)
            )

            patches.append(np.asarray(patch))
            coordinates.append((x, y))

    return patches, coordinates


# --------------------------------------------------
# VEGETATION INDICES
# --------------------------------------------------

def calculate_indices(patch):
    """Calculate RGB-based vegetation screening features."""

    image = np.asarray(patch, dtype=np.float32) / 255.0

    red = image[:, :, 0]
    green = image[:, :, 1]
    blue = image[:, :, 2]

    exg = 2 * green - red - blue

    # Normalized excess green score, for visualization only.
    exg_score = np.clip((exg.mean() + 1.0) / 3.0, 0, 1)

    brightness = (red + green + blue) / 3.0

    canopy_ratio = np.mean(
        (green > red * 1.05) &
        (green > blue * 1.05) &
        (brightness > 0.12)
    )

    return float(exg_score), float(canopy_ratio)


# --------------------------------------------------
# HEURISTIC RISK SCORING
# --------------------------------------------------

def calculate_risk(exg_score, canopy_ratio):
    """
    Prototype heuristic classification.

    These thresholds are illustrative and must be calibrated
    using labelled imagery before real-world deployment.
    """

    vegetation_score = (
        0.45 * exg_score +
        0.55 * canopy_ratio
    )

    risk_score = 1.0 - vegetation_score

    if vegetation_score >= 0.60:
        category = 0
    elif vegetation_score >= 0.35:
        category = 1
    else:
        category = 2

    return float(risk_score), category


# --------------------------------------------------
# AI FEATURE EXTRACTION
# --------------------------------------------------

def extract_embeddings(model, patches, batch_size=32):
    """Extract 2048-dimensional ResNet embeddings."""

    if not patches:
        return np.empty((0, 2048), dtype=np.float32)

    images = np.asarray(patches, dtype=np.float32)
    images = preprocess_input(images)

    embeddings = model.predict(
        images,
        batch_size=batch_size,
        verbose=0
    )

    return embeddings


# --------------------------------------------------
# RISK OVERLAY
# --------------------------------------------------

def create_risk_overlay(image, results, coordinates):
    """Paint each analyzed patch according to its risk category."""

    image = load_image(image)
    overlay = np.asarray(image).copy()

    for result, (x, y) in zip(results, coordinates):

        category_id = result["category_id"]
        color = COLORS[category_id]

        overlay[
            y:y + PATCH_SIZE,
            x:x + PATCH_SIZE
        ] = color

    overlay_image = Image.fromarray(overlay)

    return Image.blend(
        image,
        overlay_image,
        alpha=0.35
    )

# --------------------------------------------------
# COMPLETE ANALYSIS PIPELINE
# --------------------------------------------------

def analyze_image(image, model):
    """Run the complete satellite image screening pipeline."""

    image = load_image(image)

    patches, coordinates = extract_patches(image)

    if not patches:
        raise ValueError(
            "Image must be at least 160 × 160 pixels."
        )

    embeddings = extract_embeddings(model, patches)

    results = []

    for index, (patch, embedding, coordinate) in enumerate(
        zip(patches, embeddings, coordinates)
    ):

        exg, canopy = calculate_indices(patch)

        risk_score, category = calculate_risk(
            exg,
            canopy
        )

        results.append({
            "tile_id": index + 1,
            "x": coordinate[0],
            "y": coordinate[1],
            "exg_score": exg,
            "canopy_ratio": canopy,
            "risk_score": risk_score,
            "category_id": category,
            "category": CLASS_NAMES[category],
            "embedding_norm": float(
                np.linalg.norm(embedding)
            ),
        })

    report = pd.DataFrame(results)

    overlay = create_risk_overlay(
        image,
        results,
        coordinates
    )

    return {
        "report": report,
        "overlay": overlay,
        "embeddings": embeddings,
        "total_tiles": len(results),
        "image_width": image.width,
        "image_height": image.height,
    }