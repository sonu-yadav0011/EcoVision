"""
ECOVISSION geospatial foundation.

Supports a multiband, georeferenced Sentinel-2 L2A GeoTIFF stack.
NDVI is calculated only when the input contains the required Red (B04)
and Near Infrared (B08) bands. This module does NOT claim to classify
forest, deforestation, Jhum cultivation, or infrastructure.

Expected input:
  - A georeferenced GeoTIFF with bands in a known order.
  - Default: band 1 = Red (B04), band 2 = NIR (B08).
  - Optional: an SCL (Scene Classification Layer) band from Sentinel-2.

Outputs:
  - ndvi.tif: georeferenced NDVI raster.
  - ndvi_screening.tif: 0 invalid, 1 low vegetation, 2 moderate,
    3 high vegetation.
  - ndvi_summary.csv: area and pixel summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class RasterInfo:
    path: str
    width: int
    height: int
    band_count: int
    crs: Optional[str]
    bounds: tuple
    nodata: Optional[float]
    band_descriptions: tuple


def _require_rasterio():
    try:
        import rasterio
    except ImportError as exc:
        raise ImportError(
            "GeoTIFF processing requires rasterio. Install it with: "
            "pip install rasterio"
        ) from exc
    return rasterio


def inspect_geotiff(path: str | Path) -> RasterInfo:
    """Return core metadata for a georeferenced raster."""
    rasterio = _require_rasterio()
    path = Path(path)
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(
                "This raster has no CRS/georeferencing. Export a georeferenced "
                "GeoTIFF before running spatial analysis."
            )
        return RasterInfo(
            path=str(path),
            width=src.width,
            height=src.height,
            band_count=src.count,
            crs=str(src.crs),
            bounds=tuple(src.bounds),
            nodata=src.nodata,
            band_descriptions=tuple(src.descriptions or ()),
        )


def _pixel_area_hectares(src, row: int) -> float:
    """Estimate pixel area in hectares, including geographic CRS support."""
    from rasterio.crs import CRS

    crs = CRS.from_user_input(src.crs)
    transform = src.transform

    # Affine pixel area in map units squared.
    map_area = abs(transform.a * transform.e - transform.b * transform.d)

    if crs.is_projected:
        # Convert CRS linear units to metres before converting m² to hectares.
        factor = crs.linear_units_factor[1]
        return map_area * (factor ** 2) / 10_000.0

    # For geographic coordinates, calculate a representative geodesic
    # pixel area for this row. This accounts for the changing east-west
    # distance with latitude.
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    corners = [
        transform * (0, row),
        transform * (1, row),
        transform * (1, row + 1),
        transform * (0, row + 1),
    ]
    lons = [p[0] for p in corners]
    lats = [p[1] for p in corners]
    area_m2, _ = geod.polygon_area_perimeter(lons, lats)
    return abs(area_m2) / 10_000.0


def analyze_sentinel2_stack(
    input_path: str | Path,
    output_dir: str | Path,
    red_band: int = 1,
    nir_band: int = 2,
    scl_band: Optional[int] = None,
    low_ndvi_max: float = 0.20,
    moderate_ndvi_max: float = 0.40,
) -> dict:
    """
    Calculate NDVI and broad vegetation screening classes.

    Band numbers are 1-based. Confirm the stack's band order before use.
    If scl_band is supplied, Sentinel-2 SCL classes 0, 1, 3, 8, 9, 10,
    and 11 are excluded from valid analysis. SCL must be aligned to the
    same grid and use the original integer class values.

    The three output classes are vegetation screening classes, NOT
    forest-cover or deforestation labels.
    """
    rasterio = _require_rasterio()
    from rasterio.enums import Resampling

    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(input_path) as src:
        if src.crs is None:
            raise ValueError("Input GeoTIFF must have a coordinate reference system.")
        if not (1 <= red_band <= src.count and 1 <= nir_band <= src.count):
            raise ValueError(
                f"Band indexes out of range. Raster contains {src.count} bands."
            )
        if red_band == nir_band:
            raise ValueError("Red and NIR must refer to different bands.")
        if scl_band is not None and not (1 <= scl_band <= src.count):
            raise ValueError("SCL band index is outside the raster band range.")

        red = src.read(red_band).astype("float32")
        nir = src.read(nir_band).astype("float32")
        red_mask = src.read_masks(red_band) > 0
        nir_mask = src.read_masks(nir_band) > 0

        valid = red_mask & nir_mask & np.isfinite(red) & np.isfinite(nir)

        # Sentinel-2 L2A SCL invalid/cloud/shadow/snow classes.
        if scl_band is not None:
            scl = src.read(scl_band)
            excluded_scl = np.isin(scl, [0, 1, 3, 8, 9, 10, 11])
            valid &= ~excluded_scl

        denominator = nir + red
        valid &= np.abs(denominator) > 1e-8

        ndvi = np.full(red.shape, -9999.0, dtype="float32")
        ndvi_values = (nir - red) / np.where(
            np.abs(denominator) > 1e-8, denominator, 1.0
        )
        valid &= np.isfinite(ndvi_values)
        ndvi[valid] = np.clip(ndvi_values[valid], -1.0, 1.0)

        # 0 = No Data, 1 = low vegetation, 2 = moderate, 3 = high.
        screening = np.zeros(red.shape, dtype="uint8")
        screening[valid & (ndvi_values < low_ndvi_max)] = 1
        screening[
            valid
            & (ndvi_values >= low_ndvi_max)
            & (ndvi_values < moderate_ndvi_max)
        ] = 2
        screening[valid & (ndvi_values >= moderate_ndvi_max)] = 3

        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            compress="deflate",
            tiled=True,
            BIGTIFF="IF_SAFER",
        )

        ndvi_path = output_dir / "ndvi.tif"
        ndvi_profile = profile.copy()
        ndvi_profile.update(dtype="float32", nodata=-9999.0)
        with rasterio.open(ndvi_path, "w", **ndvi_profile) as dst:
            dst.write(ndvi, 1)
            dst.set_band_description(1, "NDVI")

        screening_path = output_dir / "ndvi_screening.tif"
        screening_profile = profile.copy()
        screening_profile.update(dtype="uint8", nodata=0)
        with rasterio.open(screening_path, "w", **screening_profile) as dst:
            dst.write(screening, 1)
            dst.set_band_description(
                1, "0=NoData, 1=Low, 2=Moderate, 3=High vegetation"
            )

        labels = {
            0: "No Data",
            1: "Low vegetation (NDVI < 0.20)",
            2: "Moderate vegetation (0.20–0.40)",
            3: "High vegetation (NDVI ≥ 0.40)",
        }

        records = []
        for class_id, label in labels.items():
            mask = screening == class_id
            pixel_count = int(mask.sum())
            area_ha = 0.0
            if class_id != 0:
                for row in range(src.height):
                    row_count = int(mask[row, :].sum())
                    if row_count:
                        area_ha += row_count * _pixel_area_hectares(src, row)
            records.append(
                {
                    "class_id": class_id,
                    "category": label,
                    "pixels": pixel_count,
                    "area_ha": round(area_ha, 4),
                    "percentage_of_valid_pixels": None,
                }
            )

        valid_pixels = int(valid.sum())
        for record in records:
            if record["class_id"] == 0 or valid_pixels == 0:
                record["percentage_of_valid_pixels"] = 0.0
            else:
                record["percentage_of_valid_pixels"] = round(
                    record["pixels"] / valid_pixels * 100.0, 2
                )

        summary = pd.DataFrame(records)
        summary_path = output_dir / "ndvi_summary.csv"
        summary.to_csv(summary_path, index=False)

        return {
            "raster_info": inspect_geotiff(input_path),
            "ndvi_path": str(ndvi_path),
            "screening_path": str(screening_path),
            "summary_path": str(summary_path),
            "summary": summary,
            "valid_pixels": valid_pixels,
            "total_pixels": int(red.size),
            "valid_pixel_percentage": round(valid_pixels / red.size * 100, 2),
            "band_configuration": {
                "red_band": red_band,
                "nir_band": nir_band,
                "scl_band": scl_band,
            },
        }
