import os
import zipfile
import keras
import numpy as np
from PIL import Image, ImageDraw

PATCH_SIZE = 160
PACKED_MODEL_PATH = ".packed_resnet50v2.keras"
FULL_CLASSIFIER_PATH = "eurosat_classifier.keras"

EUROSAT_CLASSES = [
    "AnnualCrop",
    "Forest",
    "HerbaceousVegetation",
    "Highway",
    "Industrial",
    "Pasture",
    "PermanentCrop",
    "Residential",
    "River",
    "SeaLake",
]

# Map EuroSAT classes to Deforestation Risk Categories
DEFORESTATION_CLASS_MAP = {
    "Forest": "Intact Forest",
    "HerbaceousVegetation": "Degraded / Jhum Regrowth",
    "Pasture": "Degraded / Jhum Regrowth",
    "AnnualCrop": "Deforested (Agricultural Clearing)",
    "PermanentCrop": "Deforested (Plantation Clearing)",
    "Residential": "Deforested (Settlement Encroachment)",
    "Industrial": "Deforested (Industrial Clearing)",
    "Highway": "Deforested (Linear Infrastructure)",
    "River": "Water Body",
    "SeaLake": "Water Body",
}


def load_satellite_model(model_dir="res_net_model.keras"):
  """Loads either a full 10-class EuroSAT model (if available) or

  packs & loads the ResNet50V2 feature extractor folder.
  """
  if os.path.exists(FULL_CLASSIFIER_PATH):
    model = keras.saving.load_model(FULL_CLASSIFIER_PATH)
    return model, "classifier"

  if os.path.isdir(model_dir):
    if not os.path.exists(PACKED_MODEL_PATH):
      with zipfile.ZipFile(PACKED_MODEL_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ["config.json", "metadata.json", "model.weights.h5"]:
          fpath = os.path.join(model_dir, fname)
          if os.path.exists(fpath):
            zf.write(fpath, arcname=fname)
    backbone = keras.saving.load_model(PACKED_MODEL_PATH)
  else:
    backbone = keras.saving.load_model(model_dir)

  return backbone, "extractor"


def _analyze_patch_spectral_and_embedding(patch_rgb: np.ndarray, emb: np.ndarray):
  """Combines ResNet50V2 2048-D structural embedding statistics with RGB canopy

  indices (Excess Green Index & Canopy Density) for zero-shot scoring.
  """
  r = patch_rgb[:, :, 0].astype(np.float32) / 255.0
  g = patch_rgb[:, :, 1].astype(np.float32) / 255.0
  b = patch_rgb[:, :, 2].astype(np.float32) / 255.0

  # Excess Green Index (ExG) & Green-Red Vegetation Ratio
  exg = np.mean(2.0 * g - r - b)
  canopy_ratio = np.mean((g > r * 1.03) & (g > b * 1.05))

  # ResNet50V2 embedding texture complexity (dense canopy has distinct activation spread)
  emb_norm = float(np.linalg.norm(emb))
  emb_sparsity = float(np.mean(emb > 0.5))

  # Composite Forest Integrity Score (0 to 100)
  spectral_score = np.clip((exg + 0.15) / 0.45, 0.0, 1.0) * 65.0
  canopy_score = np.clip(canopy_ratio, 0.0, 1.0) * 25.0
  texture_score = np.clip(emb_sparsity * 2.5, 0.0, 1.0) * 10.0

  forest_score = float(
      np.clip(spectral_score + canopy_score + texture_score, 0, 100)
  )

  if forest_score >= 62.0:
    status = "Intact Forest"
    risk = "Low"
  elif forest_score >= 38.0:
    status = "Degraded / Jhum Scrub"
    risk = "Moderate"
  else:
    status = "Deforested / Cleared Land"
    risk = "High"

  return {
      "status": status,
      "risk": risk,
      "forest_score": round(forest_score, 1),
      "canopy_pct": round(float(canopy_ratio * 100), 1),
      "embedding_norm": round(emb_norm, 2),
  }


def analyze_satellite_image(
    pil_image: Image.Image, model, mode: str, area_sq_km: float = 25.0
):
  """Splits an image into 160x160 patches, runs ResNet50V2 inference on all patches,

  and builds a deforestation risk overlay + regional metrics.
  """
  img = pil_image.convert("RGB")
  orig_w, orig_h = img.size

  # Ensure image is at least 160x160 and snapped to multiples of 160
  grid_cols = max(1, round(orig_w / PATCH_SIZE))
  grid_rows = max(1, round(orig_h / PATCH_SIZE))
  proc_w, proc_h = grid_cols * PATCH_SIZE, grid_rows * PATCH_SIZE
  resized_img = img.resize((proc_w, proc_h), Image.Resampling.BILINEAR)
  img_np = np.array(resized_img)

  patches = []
  coords = []
  for r_idx in range(grid_rows):
    for c_idx in range(grid_cols):
      y0, y1 = r_idx * PATCH_SIZE, (r_idx + 1) * PATCH_SIZE
      x0, x1 = c_idx * PATCH_SIZE, (c_idx + 1) * PATCH_SIZE
      patches.append(img_np[y0:y1, x0:x1])
      coords.append((x0, y0, x1, y1, r_idx, c_idx))

  batch = np.stack(patches, axis=0).astype(np.float32)

  if mode == "classifier":
    preds = model.predict(batch, verbose=0)
  else:
    preprocessed = keras.applications.resnet_v2.preprocess_input(batch.copy())
    embeddings = model.predict(preprocessed, verbose=0)

  overlay = resized_img.copy().convert("RGBA")
  draw = ImageDraw.Draw(overlay, "RGBA")

  patch_records = []
  for i, (x0, y0, x1, y1, r_idx, c_idx) in enumerate(coords):
    if mode == "classifier":
      probs = preds[i]
      top_idx = int(np.argmax(probs))
      eurosat_label = EUROSAT_CLASSES[top_idx]
      conf = float(probs[top_idx]) * 100.0
      mapped = DEFORESTATION_CLASS_MAP[eurosat_label]

      if mapped == "Intact Forest":
        risk, status = "Low", f"Intact Forest ({conf:.0f}%)"
      elif "Degraded" in mapped:
        risk, status = "Moderate", f"{mapped} ({conf:.0f}%)"
      elif mapped == "Water Body":
        risk, status = "Water", f"Water Body ({conf:.0f}%)"
      else:
        risk, status = "High", f"{mapped} ({conf:.0f}%)"

      record = {
          "Tile": f"R{r_idx+1}-C{c_idx+1}",
          "Classification": status,
          "Risk Level": risk,
          "Canopy Score": round(
              float(probs[EUROSAT_CLASSES.index("Forest")]) * 100, 1
          ),
          "ResNet Feature Norm": round(float(np.linalg.norm(probs)), 2),
      }
    else:
      info = _analyze_patch_spectral_and_embedding(patches[i], embeddings[i])
      risk = info["risk"]
      record = {
          "Tile": f"R{r_idx+1}-C{c_idx+1}",
          "Classification": info["status"],
          "Risk Level": risk,
          "Canopy Score": info["forest_score"],
          "ResNet Feature Norm": info["embedding_norm"],
      }

    patch_records.append(record)

    # Color-code overlay tile
    if risk == "High":
      fill_color = (220, 38, 38, 95)  # Red alert
      outline_color = (239, 68, 68, 220)
    elif risk == "Moderate":
      fill_color = (245, 158, 11, 80)  # Amber warning
      outline_color = (251, 191, 36, 200)
    elif risk == "Water":
      fill_color = (59, 130, 246, 70)  # Blue water
      outline_color = (96, 165, 250, 180)
    else:
      fill_color = (16, 185, 129, 45)  # Green intact
      outline_color = (52, 211, 153, 160)

    draw.rectangle([x0, y0, x1, y1], fill=fill_color, outline=outline_color, width=2)

  total_tiles = len(patch_records)
  high_risk = sum(1 for p in patch_records if p["Risk Level"] == "High")
  mod_risk = sum(1 for p in patch_records if p["Risk Level"] == "Moderate")
  intact = sum(1 for p in patch_records if p["Risk Level"] == "Low")

  deforested_pct = round((high_risk / total_tiles) * 100, 1)
  degraded_pct = round((mod_risk / total_tiles) * 100, 1)
  intact_pct = round((intact / total_tiles) * 100, 1)

  # Estimate cleared area & CO2 loss (~18,500 tonnes CO2 per sq. km of NE subtropical forest)
  cleared_sq_km = round((deforested_pct / 100.0) * area_sq_km, 2)
  est_co2_loss_tonnes = int(cleared_sq_km * 18500)

  summary = {
      "total_tiles": total_tiles,
      "grid_shape": f"{grid_rows} × {grid_cols}",
      "intact_pct": intact_pct,
      "degraded_pct": degraded_pct,
      "deforested_pct": deforested_pct,
      "cleared_sq_km": cleared_sq_km,
      "est_co2_loss_tonnes": est_co2_loss_tonnes,
      "model_mode": mode,
  }

  return overlay.convert("RGB"), summary, patch_records