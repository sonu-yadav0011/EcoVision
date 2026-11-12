# ECOVISSION — Phase 1 Geospatial Foundation

This module adds a georeferenced raster-processing foundation to the existing
Streamlit prototype.

## What is included

- GeoTIFF metadata inspection (dimensions, CRS, bounds, band descriptions).
- NDVI calculation from a multiband Sentinel-2 L2A GeoTIFF stack.
- Optional Sentinel-2 Scene Classification Layer (SCL) masking.
- Explicit No Data handling.
- Broad NDVI vegetation screening classes.
- Georeferenced NDVI and screening GeoTIFF exports.
- CSV summary with pixel counts and estimated area in hectares.

## Important: band order

The default expects:
- Band 1 = Red (Sentinel-2 B04)
- Band 2 = Near Infrared (Sentinel-2 B08)

If your stack has another order, pass the correct 1-based band indexes.
If you include an SCL band, pass its 1-based index using `scl_band`.

Do not assume a downloaded image is a valid multispectral stack. A normal
True Color RGB image has no NIR band and cannot produce NDVI. A screenshot,
JPEG, or PNG is also not a substitute for the original georeferenced raster.

## Install

Activate your existing virtual environment, then:

```powershell
pip install -r requirements-geospatial.txt
```

On Windows, Rasterio installation can depend on Python version and available
wheels. If pip installation fails, use a compatible conda-forge environment
rather than randomly mixing GDAL binaries.

## Example usage

```python
from geospatial import analyze_sentinel2_stack

result = analyze_sentinel2_stack(
    input_path="data/sentinel2/nagaland_stack.tif",
    output_dir="outputs/geospatial",
    red_band=1,
    nir_band=2,
    scl_band=None,  # set this only if the stack contains an aligned SCL band
)

print(result["raster_info"])
print(result["summary"])
```

## Interpretation limits

NDVI measures vegetation greenness/activity. The thresholds in this prototype
are broad vegetation screening thresholds, not validated forest classes.
High NDVI does not prove intact forest; low NDVI does not prove deforestation.
Jhum cultivation, forest degradation, and infrastructure encroachment require
additional labels, temporal evidence, and validation.

Area estimates are based on the input raster's georeferencing and pixel size.
Check the CRS and resolution before using them in reports. No Data pixels are
reported separately and excluded from valid-pixel percentages.
