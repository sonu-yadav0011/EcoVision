from __future__ import annotations

import io
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
from PIL import Image, ImageDraw, ImageFilter

from process_satellite import analyze_image, load_feature_extractor


# -------------------------------------------------------------------
# Page configuration
# -------------------------------------------------------------------
st.set_page_config(
    page_title="ECOVISSION | Northeast Forest Watch",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -------------------------------------------------------------------
# Styling
# -------------------------------------------------------------------
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'DM Sans', sans-serif;
        }
        .stApp {
            background:
                radial-gradient(circle at 85% 0%, rgba(32, 111, 75, .16), transparent 28%),
                #0b1210;
            color: #edf5ef;
        }
        h1, h2, h3 {
            font-family: 'Space Grotesk', sans-serif !important;
        }
        .hero {
            padding: 1.4rem 1.6rem;
            border: 1px solid rgba(130, 190, 150, .22);
            border-radius: 18px;
            background: linear-gradient(120deg, rgba(24, 69, 47, .72), rgba(17, 31, 25, .85));
            margin-bottom: 1.2rem;
        }
        .eyebrow {
            color: #9bd4aa;
            font-size: .78rem;
            font-weight: 700;
            letter-spacing: .16em;
            text-transform: uppercase;
        }
        .hero h1 {
            margin: .25rem 0 .35rem 0;
            font-size: 2.5rem;
            color: #f1fff4;
        }
        .hero p {
            color: #c3d7c9;
            margin: 0;
            max-width: 850px;
        }
        .metric-card {
            padding: 1rem 1.1rem;
            border: 1px solid rgba(150, 190, 160, .18);
            border-radius: 14px;
            background: rgba(20, 36, 28, .78);
            min-height: 105px;
        }
        .metric-label {
            color: #a9c1af;
            font-size: .82rem;
        }
        .metric-value {
            color: #f2fff4;
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.65rem;
            font-weight: 700;
            margin-top: .25rem;
        }
        .note {
            border-left: 3px solid #8fc99e;
            padding: .75rem 1rem;
            background: rgba(34, 75, 49, .22);
            border-radius: 0 10px 10px 0;
            color: #d5e8d9;
            font-size: .9rem;
        }
        [data-testid="stSidebar"] {
            background: #0e1914;
            border-right: 1px solid rgba(150, 190, 160, .12);
        }
        div[data-testid="stMetric"] {
            background: rgba(20, 36, 28, .78);
            border: 1px solid rgba(150, 190, 160, .18);
            padding: 14px 16px;
            border-radius: 14px;
        }
        .block-container {max-width:1480px;padding-top:2rem;padding-bottom:3rem;}
        [data-testid="stSidebar"] {background:linear-gradient(180deg,#0d1b14 0%,#101d17 100%);border-right:1px solid rgba(150,190,160,.14);}
        [data-testid="stSidebar"] .stRadio > label {color:#a8c6b1;font-weight:700;letter-spacing:.04em;}
        [data-testid="stSidebar"] [role="radiogroup"] label {padding:.55rem .7rem;border-radius:10px;margin-bottom:.25rem;}
        .stButton button,.stDownloadButton button {border-radius:11px;font-weight:650;min-height:2.6rem;border:1px solid rgba(143,201,158,.35);}
        div[data-testid="stFileUploader"] {border:1px dashed rgba(143,201,158,.45);border-radius:14px;padding:.35rem;background:rgba(20,36,28,.35);}
        div[data-testid="stDataFrame"] {border:1px solid rgba(150,190,160,.18);border-radius:12px;overflow:hidden;}
        .section-kicker {color:#9bd4aa;font-size:.76rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;margin-bottom:.3rem;}
        .stTabs [data-baseweb="tab-list"] {gap:.5rem;}
        .stTabs [data-baseweb="tab"] {border-radius:9px 9px 0 0;padding-left:1rem;padding-right:1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------------------------------------------------
# Constants and helpers
# -------------------------------------------------------------------
CATEGORY_COLORS = {
    "Intact Forest": "#2e9d62",
    "Degraded / Jhum Scrub": "#e4b64d",
    "Deforested / Cleared Land": "#d96a5f",
    "No Data": "#7d878c",
}
CATEGORY_ORDER = list(CATEGORY_COLORS.keys())


# -------------------------------------------------------------------
# Persistent local database
# -------------------------------------------------------------------
DB_PATH = Path(__file__).resolve().parent / "data" / "ecovission.db"


def init_database():
    """Create the local SQLite database and comparison-history table."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
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
            """
        )
        connection.commit()


def save_comparison_to_database(entry):
    """Persist one comparison. A stable key prevents duplicate inserts on reruns."""
    identity = "|".join(str(entry.get(key, "")) for key in (
        "monitoring_area", "earlier_image", "later_image",
        "earlier_label", "later_label", "flagged_pixels_pct",
        "sensitivity", "total_pixels"
    ))
    record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    created_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO comparison_history (
                id, created_at, monitoring_area, earlier_image, later_image,
                earlier_label, later_label, flagged_pixels_pct, flagged_pixels,
                total_pixels, sensitivity, image_width, image_height
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id, created_at, entry.get("monitoring_area"),
                entry.get("earlier_image"), entry.get("later_image"),
                entry.get("earlier_label"), entry.get("later_label"),
                entry.get("flagged_pixels_pct"), entry.get("flagged_pixels"),
                entry.get("total_pixels"), entry.get("sensitivity"),
                entry.get("image_width"), entry.get("image_height"),
            ),
        )
        connection.commit()


def load_comparison_history():
    """Read persistent comparison records from SQLite."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT created_at, monitoring_area, earlier_image, later_image,
                   earlier_label, later_label, flagged_pixels_pct,
                   flagged_pixels, total_pixels, sensitivity,
                   image_width, image_height
            FROM comparison_history
            ORDER BY created_at ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


init_database()


@st.cache_resource(show_spinner="Loading ResNet50V2 feature extractor...")
def get_model():
    """Load the feature extractor once and reuse it across Streamlit reruns."""
    return load_feature_extractor()


def create_demo_image(size: int = 640) -> Image.Image:
    """Create a clearly synthetic image for demonstrating the application UI."""
    image = Image.new("RGB", (size, size), (42, 91, 53))
    draw = ImageDraw.Draw(image)
    cell = size // 4

    # Four-by-four illustrative landscape: green, mixed, and cleared areas.
    patterns = [
        "forest", "forest", "mixed", "cleared",
        "forest", "mixed", "mixed", "cleared",
        "forest", "forest", "cleared", "cleared",
        "mixed", "forest", "cleared", "cleared",
    ]

    for index, pattern in enumerate(patterns):
        row, col = divmod(index, 4)
        x0, y0 = col * cell, row * cell
        x1, y1 = x0 + cell, y0 + cell

        if pattern == "forest":
            base = (38, 105, 53)
            palette = [(26, 83, 43), (48, 125, 58), (65, 143, 66)]
        elif pattern == "mixed":
            base = (105, 119, 57)
            palette = [(75, 111, 48), (133, 132, 62), (91, 91, 47)]
        else:
            base = (151, 119, 83)
            palette = [(165, 137, 99), (123, 108, 79), (184, 153, 112)]

        draw.rectangle((x0, y0, x1, y1), fill=base)
        # Repeated irregular shapes make the synthetic texture visible.
        for k in range(34):
            px = x0 + ((k * 37 + index * 19) % max(1, cell - 18))
            py = y0 + ((k * 53 + index * 11) % max(1, cell - 18))
            radius = 4 + ((k * 7) % 11)
            color = palette[k % len(palette)]
            draw.ellipse((px, py, px + radius, py + radius), fill=color)

    return image.filter(ImageFilter.GaussianBlur(radius=1.2))


def metric_card(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_result_value(result: dict, *keys, default=None):
    for key in keys:
        if key in result and result[key] is not None:
            return result[key]
    return default


def normalize_report(report) -> pd.DataFrame:
    if isinstance(report, pd.DataFrame):
        return report.copy()
    return pd.DataFrame(report)


def category_summary(report: pd.DataFrame) -> pd.DataFrame:
    if report.empty or "category" not in report.columns:
        return pd.DataFrame({"category": CATEGORY_ORDER, "tiles": [0] * len(CATEGORY_ORDER)})

    counts = report["category"].value_counts()
    return pd.DataFrame(
        {
            "category": CATEGORY_ORDER,
            "tiles": [int(counts.get(category, 0)) for category in CATEGORY_ORDER],
        }
    )



def show_main_dashboard():
    st.markdown(
        """<div class="hero"><div class="eyebrow">Northeast Forest Watch · Nagaland focus</div>
        <h1>ECOVISSION</h1><p>Image-based forest screening and visual comparison in one focused workspace.</p></div>""",
        unsafe_allow_html=True,
    )
    try:
        records = load_comparison_history()
    except Exception as exc:
        st.error(f"Could not load saved comparison history: {exc}")
        records = []
    frame = pd.DataFrame(records)
    count = len(frame)
    areas = int(frame["monitoring_area"].nunique()) if count else 0
    latest = float(frame.iloc[-1]["flagged_pixels_pct"]) if count else None
    flagged = int(frame["flagged_pixels"].sum()) if count else 0

    st.markdown('<div class="section-kicker">Workspace overview</div>', unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Saved comparisons",f"{count:,}")
    c2.metric("Monitoring areas",f"{areas:,}")
    c3.metric("Latest flagged pixels",f"{latest:.2f}%" if latest is not None else "—")
    c4.metric("Flagged pixels recorded",f"{flagged:,}" if count else "—")

    left,right=st.columns([1.1,.9],gap="large")
    with left:
        st.markdown("### Your workspace")
        st.markdown("""<div class="metric-card"><div class="metric-label">01 · SINGLE IMAGE ANALYSIS</div>
        <div class="metric-value">Screen one image</div><p style="color:#b9cdbf">Upload a JPG or PNG to inspect tile-level screening categories and the visual overlay.</p></div>""",unsafe_allow_html=True)
        st.markdown("""<div class="metric-card" style="margin-top:14px"><div class="metric-label">02 · TWO IMAGE COMPARISON</div>
        <div class="metric-value">Compare two dates</div><p style="color:#b9cdbf">Inspect side-by-side images, RGB differences, flagged regions, and export a report.</p></div>""",unsafe_allow_html=True)
    with right:
        st.markdown("### Recent comparison activity")
        if count:
            recent=frame.tail(5).iloc[::-1]
            st.dataframe(recent[["created_at","monitoring_area","earlier_label","later_label","flagged_pixels_pct"]].rename(columns={
                "created_at":"Saved at","monitoring_area":"Area","earlier_label":"Earlier",
                "later_label":"Later","flagged_pixels_pct":"Flagged (%)"}),
                hide_index=True,width="stretch")
        else:
            st.info("No saved comparisons yet. Completed comparisons will appear here.")
    if count:
        plot=frame.copy().reset_index(drop=True)
        plot["comparison_number"]=range(1,len(plot)+1)
        st.markdown("### Comparison activity")
        st.plotly_chart(px.line(plot,x="comparison_number",y="flagged_pixels_pct",markers=True,
            title="Flagged-pixel percentage by saved comparison",
            labels={"comparison_number":"Comparison","flagged_pixels_pct":"Flagged pixels (%)"}),
            use_container_width=True)
    st.markdown("""<div class="note"><b>Interpretation:</b> flagged pixels represent RGB colour differences or heuristic screening results.
    They are not verified deforestation, geographic area, or carbon estimates.</div>""",unsafe_allow_html=True)


def show_overview():
    st.markdown(
        """
        <div class="hero">
            <div class="eyebrow">Northeast Forest Watch</div>
            <h1>ECOVISSION</h1>
            <p>
                An AI-assisted satellite imagery screening prototype to help
                explore forest condition across Nagaland and the Northeast.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("What the prototype does")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### 🛰️ Image screening")
        st.write("Upload an image and divide it into small tiles for analysis.")
    with c2:
        st.markdown("### 🌳 Forest-condition classes")
        st.write("View heuristic screening categories and a visual tile overlay.")
    with c3:
        st.markdown("### 📊 Exportable results")
        st.write("Inspect the tile-level report and download it as a CSV file.")

    st.markdown("---")
    st.subheader("Current prototype status")
    st.markdown(
        """
        <div class="note">
            This is a demonstration prototype. The current categories are based
            on simple RGB image heuristics and are not validated deforestation
            predictions. Use real, appropriately sourced imagery for a meaningful
            screening exercise.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Analysis workflow")
    st.write("1. Select the built-in synthetic demo or upload an image.")
    st.write("2. Run the tile-based image analysis.")
    st.write("3. Review the original image, category overlay, charts and CSV report.")



# -------------------------------------------------------------------
# Forest monitoring map (indicative locations, not forest-cover data)
# -------------------------------------------------------------------
NAGALAND_LOCATIONS = pd.DataFrame(
    [
        {"location": "Kohima", "district": "Kohima", "lat": 25.6751, "lon": 94.1086},
        {"location": "Dimapur", "district": "Chümoukedima / Dimapur area", "lat": 25.9044, "lon": 93.7267},
        {"location": "Mokokchung", "district": "Mokokchung", "lat": 26.3220, "lon": 94.5176},
        {"location": "Mon", "district": "Mon", "lat": 26.7358, "lon": 95.0347},
        {"location": "Tuensang", "district": "Tuensang", "lat": 26.2670, "lon": 94.8242},
        {"location": "Wokha", "district": "Wokha", "lat": 26.0970, "lon": 94.2580},
        {"location": "Zunheboto", "district": "Zunheboto", "lat": 26.0090, "lon": 94.5150},
        {"location": "Phek", "district": "Phek", "lat": 25.6660, "lon": 94.4630},
        {"location": "Kiphire", "district": "Kiphire", "lat": 25.8730, "lon": 94.7800},
        {"location": "Longleng", "district": "Longleng", "lat": 26.4860, "lon": 94.8170},
        {"location": "Peren", "district": "Peren", "lat": 25.5120, "lon": 93.7370},
        {"location": "Noklak", "district": "Noklak", "lat": 26.2350, "lon": 95.0500},
    ]
)


def show_forest_map():
    st.markdown("## Nagaland forest monitoring map")
    st.caption(
        "Initial geographic workspace showing indicative town locations. "
        "These markers are not forest-cover observations or detected hotspots."
    )

    selected = st.selectbox(
        "Focus location",
        ["All monitored locations"] + NAGALAND_LOCATIONS["location"].tolist(),
    )

    if selected == "All monitored locations":
        map_data = NAGALAND_LOCATIONS[["lat", "lon"]].rename(
            columns={"lat": "latitude", "lon": "longitude"}
        )
        st.map(map_data, zoom=7, height=520)
        st.dataframe(
            NAGALAND_LOCATIONS[["location", "district"]],
            hide_index=True,
            width="stretch",
        )
    else:
        selected_row = NAGALAND_LOCATIONS[
            NAGALAND_LOCATIONS["location"] == selected
        ].iloc[0]
        map_data = pd.DataFrame(
            {"latitude": [selected_row["lat"]], "longitude": [selected_row["lon"]]}
        )
        st.map(map_data, zoom=10, height=520)
        st.info(
            f"Map focus: {selected_row['location']}. "
            "The marker identifies an approximate town-centre location only."
        )

    st.markdown(
        """
        <div class="note">
            Map foundation only: district boundaries, forest-cover layers,
            satellite footprints and verified change hotspots have not yet
            been connected. Do not interpret these markers as detected risk.
        </div>
        """,
        unsafe_allow_html=True,
    )


# -------------------------------------------------------------------
# Visual comparison of two ordinary images
# -------------------------------------------------------------------
def show_image_comparison():
    st.markdown("## Two Image Comparison")
    st.caption(
        "Upload two images of the same area from different dates. "
        "This tool provides a visual side-by-side comparison and a simple "
        "pixel-difference preview; it is not validated forest-change detection."
    )
    area_name = st.text_input(
        "Monitoring area name",
        value=st.session_state.get("active_monitoring_area", "My monitoring area"),
        key="comparison_area_name",
        help="A label for your site, not a mapped boundary.",
    )
    if area_name.strip():
        st.session_state["active_monitoring_area"] = area_name.strip()

    col_a, col_b = st.columns(2)
    with col_a:
        image_a_file = st.file_uploader(
            "Earlier image", type=["jpg", "jpeg", "png"], key="compare_earlier"
        )
        date_a = st.text_input(
            "Earlier image date / label", value="Earlier", key="compare_date_a"
        )
    with col_b:
        image_b_file = st.file_uploader(
            "Later image", type=["jpg", "jpeg", "png"], key="compare_later"
        )
        date_b = st.text_input(
            "Later image date / label", value="Later", key="compare_date_b"
        )

    if image_a_file is None or image_b_file is None:
        st.info("Upload both images to enable comparison.")
        return

    try:
        image_a = Image.open(image_a_file).convert("RGB")
        image_b = Image.open(image_b_file).convert("RGB")
    except Exception as exc:
        st.error(f"Could not read one of the images: {exc}")
        return

    # Resize the second image to the first image's dimensions for a preview.
    # This does not spatially register or align the images.
    if image_a.size != image_b.size:
        st.warning(
            "The images have different dimensions. The later image is resized "
            "for display only; this does not align geographic locations."
        )
        image_b_display = image_b.resize(image_a.size, Image.Resampling.LANCZOS)
    else:
        image_b_display = image_b

    st.markdown("### Side-by-side view")
    view_a, view_b = st.columns(2)
    with view_a:
        st.markdown(f"**{date_a or 'Earlier image'}**")
        st.image(image_a, width="stretch")
    with view_b:
        st.markdown(f"**{date_b or 'Later image'}**")
        st.image(image_b, width="stretch")

    # Simple RGB difference screening. This is an exploratory visual
    # comparison, not validated forest-change detection.
    from PIL import ImageChops, ImageEnhance

    difference = ImageChops.difference(image_a, image_b_display)
    difference = ImageEnhance.Contrast(difference).enhance(2.0)

    st.markdown("### Potential change screening")
    sensitivity = st.slider(
        "Difference sensitivity",
        min_value=10,
        max_value=100,
        value=35,
        step=5,
        help="Lower values flag smaller colour differences. This is not a calibrated forest-loss threshold.",
    )

    arr_a = np.asarray(image_a, dtype=np.int16)
    arr_b = np.asarray(image_b_display, dtype=np.int16)
    per_pixel_difference = np.mean(np.abs(arr_a - arr_b), axis=2)
    changed_mask = per_pixel_difference >= sensitivity

    changed_percentage = float(changed_mask.mean() * 100.0)
    changed_pixels = int(changed_mask.sum())
    total_pixels = int(changed_mask.size)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Pixels flagged as changed", f"{changed_percentage:.1f}%")
    with c2:
        st.metric("Flagged pixels", f"{changed_pixels:,}")
    with c3:
        st.metric("Pixels compared", f"{total_pixels:,}")

    # Build a red overlay to make flagged pixels easy to inspect.
    base_array = np.asarray(image_b_display).copy()
    red_layer = np.zeros_like(base_array)
    red_layer[:, :, 0] = 255
    base_array[changed_mask] = (
        0.35 * base_array[changed_mask] + 0.65 * red_layer[changed_mask]
    ).astype(np.uint8)
    change_overlay = Image.fromarray(base_array)

    st.markdown("### Change overlay")
    st.image(
        change_overlay,
        caption="Red pixels indicate RGB differences above the selected threshold.",
        width="stretch",
    )

    st.markdown("### Visual difference image")
    st.image(
        difference,
        caption="Brightness indicates the magnitude of RGB differences.",
        width="stretch",
    )

    # Summarize flagged pixels in a coarse grid for a quick hotspot table.
    grid_rows = 4
    grid_cols = 4
    height, width = changed_mask.shape
    hotspot_records = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            y0 = row * height // grid_rows
            y1 = (row + 1) * height // grid_rows
            x0 = col * width // grid_cols
            x1 = (col + 1) * width // grid_cols
            cell = changed_mask[y0:y1, x0:x1]
            hotspot_records.append({
                "grid_cell": f"R{row + 1}-C{col + 1}",
                "flagged_pixel_percentage": round(float(cell.mean() * 100), 2),
                "flagged_pixels": int(cell.sum()),
                "total_pixels": int(cell.size),
            })

    hotspot_report = pd.DataFrame(hotspot_records).sort_values(
        "flagged_pixel_percentage", ascending=False
    )
    st.session_state["latest_comparison"] = {
        "changed_percentage": changed_percentage,
        "changed_pixels": changed_pixels,
        "total_pixels": total_pixels,
        "sensitivity": int(sensitivity),
        "grid_report": hotspot_report.copy(),
        "earlier_name": getattr(image_a_file, "name", "Earlier image"),
        "later_name": getattr(image_b_file, "name", "Later image"),
        "earlier_label": date_a or "Earlier image",
        "later_label": date_b or "Later image",
        "area_name": area_name.strip() or "Unnamed area",
        "width": int(width),
        "height": int(height),
    }
    # Attach image previews only after the latest_comparison dictionary exists.
    st.session_state["latest_comparison"].update({
        "earlier_image_png": _image_to_png_bytes(image_a),
        "later_image_png": _image_to_png_bytes(image_b_display),
        "overlay_png": _image_to_png_bytes(change_overlay),
        "difference_png": _image_to_png_bytes(difference),
    })
    history_entry = {
        "monitoring_area": area_name.strip() or "Unnamed area",
        "earlier_image": getattr(image_a_file, "name", "Earlier image"),
        "later_image": getattr(image_b_file, "name", "Later image"),
        "earlier_label": date_a or "Earlier",
        "later_label": date_b or "Later",
        "flagged_pixels_pct": round(changed_percentage, 2),
        "flagged_pixels": changed_pixels,
        "total_pixels": total_pixels,
        "sensitivity": int(sensitivity),
    }
    save_comparison_to_database({
        **history_entry,
        "image_width": int(width),
        "image_height": int(height),
    })
    history = st.session_state.setdefault("monitoring_history", [])
    history.append(history_entry)
    st.session_state["monitoring_history"] = history[-100:]
    st.markdown("### Highest-difference image regions")
    st.dataframe(hotspot_report, hide_index=True, width="stretch")

    st.download_button(
        "Download visual difference image",
        data=_image_to_png_bytes(difference),
        file_name="ecovission_visual_difference.png",
        mime="image/png",
        use_container_width=True,
    )
    st.download_button(
        "Download comparison report (CSV)",
        data=hotspot_report.to_csv(index=False).encode("utf-8"),
        file_name="ecovission_comparison_report.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.markdown(
        """
        <div class="note">
            These are image-colour differences, not confirmed forest loss.
            Camera angle, season, sunlight, haze, clouds, compression and
            imperfect alignment can all create false change signals. Use
            images of the same area with matching framing and conditions.
            The 4 × 4 grid cells are image regions, not geographic coordinates.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _image_to_png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()




def build_comparison_pdf(data):
    """Create a concise PDF report from the latest in-session comparison."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as ReportImage

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm,
                            leftMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"],
                              alignment=TA_CENTER, textColor=colors.HexColor("#24583b")))
    story = [
        Paragraph("ECOVISSION — Image Comparison Report", styles["ReportTitle"]),
        Paragraph("Exploratory RGB difference screening", styles["Heading2"]),
        Spacer(1, 4*mm),
        Paragraph("This report summarizes pixel-level colour differences between two uploaded images. It is not a validated forest-loss assessment.", styles["BodyText"]),
        Spacer(1, 4*mm),
    ]
    rows = [
        ["Metric", "Result"],
        ["Earlier image", str(data.get("earlier_name", "Earlier image"))],
        ["Earlier label", str(data.get("earlier_label", "Earlier"))],
        ["Later image", str(data.get("later_name", "Later image"))],
        ["Later label", str(data.get("later_label", "Later"))],
        ["Pixels flagged", f'{data["changed_percentage"]:.2f}%'],
        ["Flagged pixel count", f'{data["changed_pixels"]:,}'],
        ["Total pixels compared", f'{data["total_pixels"]:,}'],
        ["Difference sensitivity", str(data["sensitivity"])],
        ["Image dimensions", f'{data["width"]} × {data["height"]} pixels'],
    ]
    table = Table(rows, colWidths=[52*mm, 112*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24583b")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#cbd5ce")),
        ("FONTSIZE",(0,0),(-1,-1),8),("PADDING",(0,0),(-1,-1),6),
    ]))
    story.extend([table, Spacer(1, 5*mm)])

    for title, key in [
        ("Earlier image", "earlier_image_png"),
        ("Later image", "later_image_png"),
        ("RGB difference overlay", "overlay_png"),
        ("Visual difference image", "difference_png"),
    ]:
        payload=data.get(key)
        if payload:
            story.append(Paragraph(title, styles["Heading2"]))
            story.append(ReportImage(io.BytesIO(payload), width=160*mm, height=90*mm, kind="proportional"))
            story.append(Spacer(1, 3*mm))

    story.append(Paragraph("Highest-difference image regions", styles["Heading2"]))
    grid=data["grid_report"].sort_values("flagged_pixel_percentage", ascending=False)
    grid_rows=[["Image grid cell","Flagged pixels (%)","Flagged count"]]
    for _, row in grid.iterrows():
        grid_rows.append([str(row["grid_cell"]), f'{float(row["flagged_pixel_percentage"]):.2f}', f'{int(row["flagged_pixels"]):,}'])
    grid_table=Table(grid_rows,colWidths=[55*mm,55*mm,54*mm],repeatRows=1)
    grid_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24583b")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#cbd5ce")),
        ("FONTSIZE",(0,0),(-1,-1),8),("PADDING",(0,0),(-1,-1),6),
    ]))
    story.extend([
        grid_table, Spacer(1,5*mm),
        Paragraph("Interpretation and limitations",styles["Heading2"]),
        Paragraph("A flagged pixel indicates that the mean absolute RGB difference between corresponding pixels meets or exceeds the selected threshold. It does not prove tree loss, degradation, encroachment, or a land-cover transition. Differences may result from image alignment, season, sunlight, haze, clouds, camera angle, or compression. Grid cells describe image regions only; they are not geographic coordinates or districts. Area and carbon impacts are not estimated.",styles["BodyText"])
    ])
    doc.build(story)
    return buffer.getvalue()


def show_forest_intelligence():
    st.markdown("## Forest Intelligence Dashboard")
    st.caption(
        "A summary of analyses performed in this app. Values below are "
        "image-comparison indicators, not measured forest-cover statistics."
    )

    latest = st.session_state.get("latest_comparison")
    if latest is None:
        st.info(
            "No image comparison is available yet. Open **Image Comparison**, "
            "upload earlier and later images, and run the screening. "
            "Your latest result will appear here during this session."
        )
        st.markdown("### What this dashboard will summarize")
        st.write(
            "- Overall percentage of pixels flagged by the RGB comparison.\n"
            "- Number of pixels flagged and total pixels compared.\n"
            "- Image regions with the highest difference scores.\n"
            "- The sensitivity setting and source image names."
        )
        st.warning(
            "No Nagaland-wide forest statistics, district rankings, or "
            "geographic hotspot claims are generated because verified "
            "geospatial data is not connected yet."
        )
        return

    changed = latest["changed_percentage"]
    flagged = latest["changed_pixels"]
    total = latest["total_pixels"]
    unaffected = max(total - flagged, 0)
    report = latest["grid_report"].copy()

    st.markdown("### Latest comparison snapshot")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Pixels flagged", f"{changed:.1f}%")
    k2.metric("Flagged pixel count", f"{flagged:,}")
    k3.metric("Pixels compared", f"{total:,}")
    k4.metric("Sensitivity threshold", str(latest["sensitivity"]))

    st.markdown(
        f"**Earlier image:** `{latest['earlier_name']}`  \n"
        f"**Later image:** `{latest['later_name']}`  \n"
        f"**Compared dimensions:** {latest['width']:,} × {latest['height']:,} pixels"
    )

    st.markdown("### Pixel screening breakdown")
    breakdown = pd.DataFrame({
        "pixel_status": ["Flagged by RGB comparison", "Not flagged"],
        "pixels": [flagged, unaffected],
    })
    c1, c2 = st.columns([1, 1])
    with c1:
        st.plotly_chart(
            px.pie(
                breakdown,
                names="pixel_status",
                values="pixels",
                hole=0.62,
                title="Share of compared pixels",
            ),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            px.bar(
                report.sort_values("flagged_pixel_percentage", ascending=True),
                x="flagged_pixel_percentage",
                y="grid_cell",
                orientation="h",
                title="Highest-difference image regions",
                labels={
                    "flagged_pixel_percentage": "Flagged pixels (%)",
                    "grid_cell": "Image grid cell",
                },
            ),
            use_container_width=True,
        )

    st.markdown("### Region-level screening table")
    st.dataframe(report, hide_index=True, width="stretch")
    st.download_button(
        "Download dashboard summary (CSV)",
        data=report.to_csv(index=False).encode("utf-8"),
        file_name="ecovission_forest_intelligence_summary.csv",
        mime="text/csv",
        use_container_width=True,
    )
    if latest.get("overlay_png"):
        st.download_button(
            "Download full comparison report (PDF)",
            data=build_comparison_pdf(latest),
            file_name="ecovission_image_comparison_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.markdown(
        """
        <div class="note">
            A flagged pixel means its RGB colour differed from the corresponding
            pixel in the other image by at least the selected threshold. It does
            not prove tree loss, degradation, encroachment, or any specific
            land-cover transition. Grid cells are image regions, not districts
            or mapped locations.
        </div>
        """,
        unsafe_allow_html=True,
    )



def show_monitoring_areas():
    st.markdown("## User-Defined Monitoring Areas")
    st.caption("Organize comparisons by site names you assign. History is saved locally in SQLite; this is not a geographic boundary database.")
    try:
        history = load_comparison_history()
    except Exception as exc:
        st.error(f"Could not read the local history database: {exc}")
        return
    if not history:
        st.info("No monitoring history yet. Open Image Comparison, enter an area name, upload two images, and run a comparison.")
        st.write("1. Choose a consistent name for a site.\n2. Upload earlier and later images.\n3. Run the comparison.\n4. Repeat later using the same area name.")
        st.warning("Area names are labels only. Coordinates, boundaries, and geographic area calculations are not available yet.")
        return

    frame = pd.DataFrame(history)
    areas = sorted(frame["monitoring_area"].dropna().unique().tolist())
    selected = st.selectbox("Choose a monitoring area", areas)
    area_frame = frame[frame["monitoring_area"] == selected].copy()

    st.markdown(f"### History: {selected}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Comparisons recorded", len(area_frame))
    c2.metric("Latest flagged pixels", f'{area_frame.iloc[-1]["flagged_pixels_pct"]:.2f}%')
    c3.metric("Images represented", int(area_frame[["earlier_image", "later_image"]].stack().nunique()))

    st.markdown("### Comparison history")
    st.dataframe(
        area_frame[["earlier_label", "later_label", "earlier_image", "later_image", "flagged_pixels_pct", "flagged_pixels", "sensitivity"]].rename(columns={
            "earlier_label":"Earlier date / label", "later_label":"Later date / label",
            "earlier_image":"Earlier file", "later_image":"Later file",
            "flagged_pixels_pct":"Flagged pixels (%)", "flagged_pixels":"Flagged pixel count",
            "sensitivity":"Sensitivity",
        }),
        hide_index=True, width="stretch"
    )
    plot_frame=area_frame.reset_index(drop=True)
    plot_frame["comparison_number"]=range(1,len(plot_frame)+1)
    st.plotly_chart(px.line(plot_frame,x="comparison_number",y="flagged_pixels_pct",markers=True,
        title="Flagged-pixel percentage across comparisons",
        labels={"comparison_number":"Comparison sequence","flagged_pixels_pct":"Flagged pixels (%)"}),
        use_container_width=True)
    st.download_button("Download monitoring history (CSV)",
        data=area_frame.to_csv(index=False).encode("utf-8"),
        file_name="ecovission_monitoring_history.csv",mime="text/csv",use_container_width=True)
    st.markdown(
        """<div class="note">These values are exploratory RGB difference indicators, not measured deforestation. Comparisons are meaningful only when framing, alignment, season, lighting, and processing are similar. History is stored locally in data/ecovission.db and remains available after app restarts. Keep this database file backed up.</div>""",
        unsafe_allow_html=True,
    )


def show_methodology():
    st.markdown("## Methodology & limitations")
    st.write(
        "The current pipeline divides the input image into 160 × 160 pixel "
        "tiles, extracts image features with the supplied ResNet50V2 feature "
        "extractor, and calculates simple RGB-based vegetation heuristics."
    )

    st.markdown("### Screening categories")
    for category, color in CATEGORY_COLORS.items():
        st.markdown(
            f"<span style='color:{color};font-weight:700'>● {category}</span>",
            unsafe_allow_html=True,
        )

    st.markdown("### Important limitations")
    st.markdown(
        """
        - The ResNet50V2 model is used as a **feature extractor**, not as a
          trained forest-classification model.
        - The current vegetation measurements are derived from RGB values.
          They are not NDVI or another calibrated multispectral vegetation index.
        - A single image cannot establish that deforestation has occurred.
          Change detection requires comparable imagery from multiple dates.
        - Area estimates require georeferencing and known ground sampling
          distance or pixel resolution.
        - Carbon-stock estimates require a defensible biomass/carbon methodology
          and suitable supporting data.
        - The categories should be treated as exploratory screening labels,
          not ground-truth land-cover classifications.
        """
    )

    st.markdown("### Planned extensions")
    st.write(
        "Potential future work includes georeferenced imagery, multi-date "
        "change detection, validated land-cover labels, field verification, "
        "and carefully sourced historical forest statistics."
    )


def show_analysis():
    st.markdown("## Single Image Analysis")
    st.caption(
        "Run a tile-level screening analysis. The built-in image is synthetic "
        "and is provided only to demonstrate the application workflow."
    )

    source = st.radio(
        "Choose image source",
        ["Built-in synthetic demo", "Upload an image"],
        horizontal=True,
        key="image_source",
    )

    selected_image = None
    image_name = None

    if source == "Built-in synthetic demo":
        selected_image = create_demo_image()
        image_name = "synthetic_demo.png"
        st.info("Synthetic demonstration image — not real satellite imagery.")
    else:
        uploaded_file = st.file_uploader(
            "Upload satellite or aerial imagery",
            type=["png", "jpg", "jpeg", "tif", "tiff"],
            help="For best results, use a clear RGB image. Multispectral processing is not implemented yet.",
        )
        if uploaded_file is not None:
            try:
                selected_image = Image.open(uploaded_file).convert("RGB")
                image_name = uploaded_file.name
            except Exception as exc:
                st.error(f"Could not open this image: {exc}")

    # Keep the currently selected image in session state so Streamlit reruns
    # do not leave the results panel with a missing local image variable.
    if selected_image is not None:
        current_signature = (source, image_name)
        previous_signature = st.session_state.get("image_signature")
        if current_signature != previous_signature:
            st.session_state.pop("analysis", None)
            st.session_state["image_signature"] = current_signature
        st.session_state["input_image"] = selected_image.copy()
        st.session_state["input_image_name"] = image_name

    can_analyze = selected_image is not None

    if can_analyze:
        left, right = st.columns([1, 1])
        with left:
            st.markdown("**Selected image**")
            st.image(selected_image, width="stretch")
        with right:
            st.markdown("**Image details**")
            st.write(f"**File:** {image_name}")
            st.write(f"**Dimensions:** {selected_image.width} × {selected_image.height}")
            st.write(f"**Mode:** RGB")
            st.write("**Tile size:** 160 × 160 pixels")

        if st.button("Run forest screening", type="primary", use_container_width=True):
            with st.spinner("Loading feature extractor and analysing image tiles..."):
                try:
                    model = get_model()
                    result = analyze_image(selected_image, model)
                    st.session_state["analysis"] = result
                    st.session_state["input_image"] = selected_image.copy()
                    st.session_state["input_image_name"] = image_name
                    st.success("Analysis completed.")
                except Exception as exc:
                    st.error("Analysis failed. Check the terminal for the full traceback.")
                    st.exception(exc)

    # Results are rendered from session state, not from a temporary local
    # variable that can disappear during a Streamlit rerun.
    if "analysis" in st.session_state:
        result = st.session_state["analysis"]
        display_image = st.session_state.get("input_image")
        if display_image is None:
            st.warning("The original image is no longer available. Select it again and rerun the analysis.")
            return

        report = normalize_report(get_result_value(result, "report", "tile_report", default=pd.DataFrame()))
        overlay = get_result_value(result, "overlay", "risk_overlay", "overlay_image")
        tile_count = get_result_value(result, "tile_count", "total_tiles", default=len(report))
        image_width = get_result_value(result, "image_width", "width", default=display_image.width)
        image_height = get_result_value(result, "image_height", "height", default=display_image.height)

        st.markdown("---")
        st.subheader("Analysis results")

        summary = category_summary(report)
        total_tiles = int(tile_count) if tile_count is not None else len(report)
        valid_tiles = int((report["category"] != "No Data").sum()) if "category" in report.columns else total_tiles
        category_counts = dict(zip(summary["category"], summary["tiles"]))

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            metric_card("Tiles analysed", f"{total_tiles:,}")
        with m2:
            metric_card("Intact forest tiles", f"{category_counts.get('Intact Forest', 0):,}")
        with m3:
            metric_card("Degraded / scrub tiles", f"{category_counts.get('Degraded / Jhum Scrub', 0):,}")
        with m4:
            metric_card("Cleared-land tiles", f"{category_counts.get('Deforested / Cleared Land', 0):,}")

        st.caption(
            f"Valid classified tiles: {valid_tiles:,} · "
            f"Possible No Data tiles: {category_counts.get('No Data', 0):,}"
        )

        image_col, overlay_col = st.columns(2)
        with image_col:
            st.markdown("**Original image**")
            st.image(display_image, width="stretch")
        with overlay_col:
            st.markdown("**Screening overlay**")
            if overlay is not None:
                st.image(overlay, width="stretch")
            else:
                st.warning("The backend did not return an overlay image.")

        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.markdown("**Tile distribution**")
            nonzero = summary[summary["tiles"] > 0]
            if not nonzero.empty:
                fig = px.pie(
                    nonzero,
                    names="category",
                    values="tiles",
                    color="category",
                    color_discrete_map=CATEGORY_COLORS,
                    hole=0.48,
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#e7f0e9",
                    legend_title_text="",
                    margin=dict(t=15, b=15, l=10, r=10),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No category data is available to chart.")

        with chart_col2:
            st.markdown("**Tiles by screening category**")
            fig = px.bar(
                summary,
                x="category",
                y="tiles",
                color="category",
                color_discrete_map=CATEGORY_COLORS,
                category_orders={"category": CATEGORY_ORDER},
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e7f0e9",
                showlegend=False,
                xaxis_title="",
                yaxis_title="Number of tiles",
                margin=dict(t=15, b=15, l=10, r=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Tile-level report")
        if report.empty:
            st.info("The backend returned an empty tile report.")
        else:
            st.dataframe(report, width="stretch", hide_index=True)
            csv_bytes = report.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download analysis report (CSV)",
                data=csv_bytes,
                file_name="ecovission_tile_report.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.markdown("### Area and carbon estimates")
        st.info(
            "Not calculated in this prototype. Reliable area estimates require "
            "georeferencing and image resolution; carbon estimates require "
            "validated biomass or carbon-stock data."
        )

        st.caption(
            "Interpretation: these are heuristic image-screening categories. "
            "They do not establish forest loss, legal land status, or verified "
            "deforestation."
        )


# -------------------------------------------------------------------
# Navigation
# -------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🌿 ECOVISSION")
    st.caption("Northeast Forest Watch")
    st.markdown("---")
    st.markdown('<div class="section-kicker">Workspace</div>', unsafe_allow_html=True)
    page = st.radio(
        "Navigation",
        ["Main Dashboard", "Single Image Analysis", "Two Image Comparison"],
        label_visibility="collapsed",
        key="main_navigation",
    )
    st.markdown("---")
    st.caption("Nagaland focus")
    st.caption("Exploratory RGB image screening")

if page == "Main Dashboard":
    show_main_dashboard()
elif page == "Single Image Analysis":
    show_analysis()
else:
    show_image_comparison()

st.markdown("---")
st.caption("ECOVISSION is a prototype decision-support concept, not an operational forest-monitoring authority.")
