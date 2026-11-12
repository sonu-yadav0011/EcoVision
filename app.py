import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
from process_satellite import analyze_satellite_image, load_satellite_model
import streamlit as st

st.set_page_config(
    page_title="VanRakshak NE | Nagaland Deforestation Monitor",
    page_icon="🌲",
    layout="wide",
)


@st.cache_resource
def get_model():
  return load_satellite_model("res_net_model.keras")


def generate_sample_nagaland_satellite(deforestation_level="High"):
  """Generates a realistic synthetic 480x320 aerial forest/clearing patch for instant demo."""
  rng = np.random.default_rng(42)
  w, h = 480, 320
  # Base dense tropical green canopy texture
  r = rng.integers(22, 52, size=(h, w), dtype=np.uint8)
  g = rng.integers(78, 128, size=(h, w), dtype=np.uint8)
  b = rng.integers(25, 50, size=(h, w), dtype=np.uint8)
  img = Image.fromarray(np.stack([r, g, b], axis=-1))
  draw = ImageDraw.Draw(img)

  # Simulate Jhum (shifting cultivation) & logging clearings (brown/ochre soil)
  if deforestation_level in ("High", "Moderate"):
    draw.polygon(
        [(150, 20), (340, 40), (360, 175), (170, 165)], fill=(148, 112, 76)
    )
    draw.polygon(
        [(310, 165), (470, 155), (475, 310), (325, 305)], fill=(162, 124, 84)
    )
  if deforestation_level == "High":
    # Simulate linear highway / settlement encroachment
    draw.line([(0, 240), (480, 110)], fill=(175, 168, 158), width=14)
    draw.rectangle([30, 180, 150, 300], fill=(158, 118, 82))

  return img


# --- SIDEBAR ---
st.sidebar.title("🌲 VanRakshak NE")
st.sidebar.caption(
    "Satellite Deforestation Intelligence for Environmental NGOs"
)

selected_district = st.sidebar.selectbox(
    "Target Monitoring Zone (Nagaland)",
    [
        "Mon District (High Jhum & Timber Belt)",
        "Tuensang District (Eastern Forest Corridor)",
        "Dimapur–Peren Foothills (Urban & Highway Expansion)",
        "Wokha–Doyang Catchment Belt",
        "Kohima–Dzükou Buffer Zone",
    ],
)

area_sq_km = st.sidebar.slider(
    "Monitored AOI Area (sq. km)", min_value=5, max_value=100, value=25, step=5
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**State Context (ISFR 2023):**\n"
    "- **State:** Nagaland, Northeast India\n"
    "- **Forest Loss (ISFR 2023):** -125.22 sq. km (#1 loss in NE India)\n"
    "- **Decadal Loss (2011–2021):** -1,067 sq. km\n"
    "- **Primary Drivers:** Shifting (*Jhum*) cultivation, logging & road clearing"
)

# --- HEADER ---
st.title("🛰️ Nagaland Forest Cover & Deforestation Dashboard")
st.markdown(
    f"**Active Monitoring Sector:** `{selected_district}` | **Model:** ResNet50V2 (`160×160` Tile Analyzer)"
)

try:
  model, mode = get_model()
  st.sidebar.success(
      f"Model Loaded ({'10-Class EuroSAT' if mode == 'classifier' else 'ResNet50V2 Feature Extractor'})"
  )
except Exception as e:
  st.error(f"Could not load `res_net_model.keras`: {e}")
  st.stop()

tab1, tab2 = st.tabs(
    ["🔍 Live Satellite Image Scanner", "📊 Nagaland Historical Trends (ISFR)"]
)

# --- TAB 1: LIVE SATELLITE SCANNER ---
with tab1:
  col_up1, col_up2 = st.columns([2, 1])
  with col_up1:
    uploaded_file = st.file_uploader(
        "Upload a Satellite / Aerial Image (JPG, PNG, TIF)",
        type=["jpg", "jpeg", "png", "tif", "tiff"],
    )
  with col_up2:
    st.write("Or test with a built-in Nagaland demo tile:")
    demo_choice = st.selectbox(
        "Sample Patch",
        [
            "High Deforestation (Jhum + Road)",
            "Moderate Clearing",
            "Dense Intact Canopy",
        ],
    )

  if uploaded_file is not None:
    input_image = Image.open(uploaded_file)
    source_label = uploaded_file.name
  else:
    level = (
        "High"
        if "High" in demo_choice
        else ("Moderate" if "Moderate" in demo_choice else "Low")
    )
    input_image = generate_sample_nagaland_satellite(level)
    source_label = f"Demo Sample — {selected_district}"

  overlay_img, summary, records = analyze_satellite_image(
      input_image, model, mode, area_sq_km=float(area_sq_km)
  )

  # Top KPI Metrics
  k1, k2, k3, k4 = st.columns(4)
  k1.metric("🌲 Intact Canopy", f"{summary['intact_pct']}%")
  k2.metric(
      "⚠️ Degraded / Jhum Scrub",
      f"{summary['degraded_pct']}%",
      delta="Watchlist",
      delta_color="off",
  )
  k3.metric(
      "🚨 Deforested / Cleared",
      f"{summary['deforested_pct']}%",
      delta=f"-{summary['cleared_sq_km']} sq. km",
      delta_color="inverse",
  )
  k4.metric(
      "💨 Est. Carbon Emissions",
      f"{summary['est_co2_loss_tonnes']:,} t CO₂",
      delta="From cleared zone",
      delta_color="inverse",
  )

  # Side-by-side Image Comparison
  c1, c2 = st.columns(2)
  with c1:
    st.subheader("Raw Satellite Imagery")
    st.image(input_image, caption=source_label, use_container_width=True)
  with c2:
    st.subheader(
        f"ResNet50V2 Deforestation Risk Map ({summary['grid_shape']} tiles)"
    )
    st.image(
        overlay_img,
        caption="🟢 Intact Forest  |  🟠 Degraded / Jhum  |  🔴 Deforested / Cleared",
        use_container_width=True,
    )

  # Tile-Level Breakdown & NGO Report Export
  st.subheader("📋 Tile-by-Tile Field Inspection Report")
  df_tiles = pd.DataFrame(records)
  st.dataframe(df_tiles, use_container_width=True, hide_index=True)

  csv_data = df_tiles.to_csv(index=False).encode("utf-8")
  st.download_button(
      label="⬇️ Download NGO Field Alert Report (CSV)",
      data=csv_data,
      file_name="nagaland_deforestation_report.csv",
      mime="text/csv",
  )

# --- TAB 2: NAGALAND HISTORICAL & DISTRICT TRENDS ---
with tab2:
  st.subheader(
      "Nagaland Forest Cover Trajectory (India State of Forest Report Data)"
  )
  st.markdown(
      "Nagaland has experienced persistent forest loss over the last decade—losing **1,067 sq. km** between 2011 and 2021 "
      "and another **125.22 sq. km** in ISFR 2023—making rapid satellite triage vital for local conservation groups."
  )

  hist_df = pd.DataFrame({
      "Assessment Year": [
          "2011",
          "2013",
          "2015",
          "2017",
          "2019",
          "2021",
          "2023",
      ],
      "Forest Cover (sq. km)": [13318, 13044, 12939, 12489, 12486, 12251, 12126],
  }).set_index("Assessment Year")

  st.line_chart(hist_df, color="#10b981")

  st.subheader("District-Level Deforestation Risk Breakdown (Nagaland)")
  district_df = pd.DataFrame({
      "District": [
          "Mon",
          "Tuensang",
          "Dimapur",
          "Wokha",
          "Kohima",
          "Mokokchung",
          "Phek",
      ],
      "Primary Driver": [
          "Shifting (Jhum) Cultivation & Logging",
          "Jhum Cycles & Road Widening",
          "Urban & Industrial Encroachment",
          "Agricultural Expansion",
          "Infrastructure & Peri-Urban Growth",
          "Jhum Cultivation",
          "Timber & Terrace Clearing",
      ],
      "Alert Priority": [
          "Critical",
          "Critical",
          "High",
          "High",
          "Moderate",
          "Moderate",
          "Moderate",
      ],
      "Recent Canopy Loss Index": [92, 88, 84, 76, 68, 65, 61],
  })
  st.dataframe(district_df, use_container_width=True, hide_index=True)