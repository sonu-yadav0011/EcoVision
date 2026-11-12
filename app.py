from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
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
        .stButton button, .stDownloadButton button {
            border-radius: 10px;
            font-weight: 600;
        }
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
}
CATEGORY_ORDER = list(CATEGORY_COLORS.keys())


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
        return pd.DataFrame({"category": CATEGORY_ORDER, "tiles": [0, 0, 0]})

    counts = report["category"].value_counts()
    return pd.DataFrame(
        {
            "category": CATEGORY_ORDER,
            "tiles": [int(counts.get(category, 0)) for category in CATEGORY_ORDER],
        }
    )


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
    st.markdown("## Satellite image analysis")
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
        if total_tiles := int(tile_count):
            summary["percentage"] = (
                summary["tiles"] / total_tiles * 100
            ).round(1)
        else:
            summary["percentage"] = 0.0

        total_tiles = int(tile_count) if tile_count is not None else len(report)
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

        st.markdown("### Category distribution")

        cols = st.columns(3)

        for col, (_, row) in zip(cols, summary.iterrows()):
            with col:
                st.metric(
                    row["category"],
                    f"{row['percentage']:.1f}%",
                    f"{row['tiles']} tiles"
                )

        st.markdown("### Overlay legend")

        legend_cols = st.columns(3)

        for col, (category, color) in zip(
            legend_cols, CATEGORY_COLORS.items()
        ):
           with col:
                st.markdown(
                    f"<span style='color:{color};font-size:20px'>●</span> "
                    f"{category}",
                    unsafe_allow_html=True
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
    page = st.radio(
        "Navigation",
        ["Overview", "Satellite Analysis", "Methodology & About"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("Prototype • Nagaland focus")
    st.caption("RGB heuristic screening • 160 px tiles")

if page == "Overview":
    show_overview()
elif page == "Satellite Analysis":
    show_analysis()
else:
    show_methodology()

st.markdown("---")
st.caption("ECOVISSION is a prototype decision-support concept, not an operational forest-monitoring authority.")
