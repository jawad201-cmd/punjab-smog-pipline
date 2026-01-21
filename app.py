import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import plotly.express as px
from datetime import datetime, timedelta
import streamlit.components.v1 as components
import math
from locations import DISTRICTS

# -------------------------------
# UI helpers: button-based reveal
# -------------------------------
def _toggle_button(label: str, key: str):
    if key not in st.session_state:
        st.session_state[key] = False
    if st.button(label, key=f"{key}_btn"):
        st.session_state[key] = not st.session_state[key]
    return st.session_state[key]

# -------------------------------
# Stats helpers for "outcome note"
# -------------------------------
def _lin_stats(x: pd.Series, y: pd.Series):
    tmp = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(tmp) < 10 or tmp["x"].nunique() < 2:
        return None
    xv = tmp["x"].astype(float).values
    yv = tmp["y"].astype(float).values
    slope = np.polyfit(xv, yv, 1)[0]
    corr = np.corrcoef(xv, yv)[0, 1]
    # effect size across observed x-range
    dx = float(np.nanmax(xv) - np.nanmin(xv))
    dy = float(slope * dx)
    y_med = float(np.nanmedian(yv))
    rel = abs(dy) / (abs(y_med) + 1e-9)
    return {"slope": slope, "corr": corr, "dy": dy, "rel": rel, "n": len(tmp)}

def _banded(series: pd.Series, q: float = 0.75):
    # returns (low_mask, high_mask) by quantile
    if series.dropna().empty:
        return None, None
    cut = series.quantile(q)
    return series <= cut, series > cut

# --------------------------------------------
# Outcome engines (computed from the data)
# --------------------------------------------
def outcome_1_wind_speed_pm(city_df: pd.DataFrame):
    # Wind Speed vs PM2.5/PM10
    s25 = _lin_stats(city_df["wind_speed"], city_df["pm2_5"])
    s10 = _lin_stats(city_df["wind_speed"], city_df["pm10"])
    if not s25 or not s10:
        return "Interpretation: Not enough valid observations to infer a stable wind–PM relationship."

    def trend_label(sts):
        if sts["rel"] < 0.05 or abs(sts["corr"]) < 0.15:
            return "flat"
        return "down" if sts["slope"] < 0 else "up"

    t25 = trend_label(s25)
    t10 = trend_label(s10)

    # match your rule-set
    if t25 == "down" and t10 == "down":
        return "Interpretation: Both PM2.5 and PM10 decrease as wind increases → dispersion/ventilation is likely dominating (stagnation-driven smog)."
    if t25 == "down" and t10 in ["flat", "up"]:
        return "Interpretation: PM2.5 drops but PM10 does not → fine particles disperse, while coarse dust may resuspend at higher wind."
    if t25 == "up" and t10 == "up":
        return "Interpretation: Both rise with wind → wind may be transporting pollution into the district (advection / dust events)."
    if t25 == "flat" and t10 == "flat":
        return "Interpretation: Wind speed is not the primary control here → emissions, humidity, inversions, or mixing height likely dominate."
    # fallback: noisy / mixed
    return "Interpretation: Relationship is mixed/noisy → direction or multiple sources may be more important than speed."

def outcome_2_wind_rose_map(city_df: pd.DataFrame):
    # Avg Pollution by Wind Direction + map sectors
    if "wind_cardinal" not in city_df.columns:
        return "Interpretation: Wind direction bins are missing, so directional source inference cannot be computed."
    d = city_df.dropna(subset=["wind_cardinal", "pm2_5", "pm10"])
    if len(d) < 20:
        return "Interpretation: Not enough directional observations to infer a stable corridor pattern."

    med25 = d.groupby("wind_cardinal")["pm2_5"].median()
    med10 = d.groupby("wind_cardinal")["pm10"].median()

    if med25.empty:
        return "Interpretation: Not enough directional observations to infer a stable corridor pattern."

    top25 = med25.idxmax()
    top10 = med10.idxmax()
    ratio25 = float(med25.max() / (med25.median() + 1e-9))
    ratio10 = float(med10.max() / (med10.median() + 1e-9))

    # “one/few directions high” vs “all similar”
    strong_dir = (ratio25 > 1.25) or (ratio10 > 1.25)
    flat_dir = (ratio25 < 1.12) and (ratio10 < 1.12)

    if flat_dir:
        return "Interpretation: PM is broadly similar across directions → local emissions + stagnation likely dominate more than directional transport."
    if strong_dir:
        if top25 != top10:
            return f"Interpretation: Strong directional signal. PM2.5 peaks from {top25} while PM10 peaks from {top10} → likely different source corridors (smoke/combustion vs dust)."
        return f"Interpretation: One/few directions dominate (peak from {top25}) → likely transported pollution from that upwind corridor."
    return "Interpretation: Directional differences exist but are moderate → likely mixed local + transport influences."

def outcome_3_dir_split_wind(city_df: pd.DataFrame):
    # Wind Direction vs median PM2.5 split by wind band (Low vs Moderate)
    if "wind_cardinal" not in city_df.columns:
        return "Interpretation: Wind direction bins are missing, so the split-by-wind analysis cannot be computed."

    d = city_df.dropna(subset=["wind_cardinal", "wind_speed", "pm2_5"]).copy()
    if len(d) < 30:
        return "Interpretation: Not enough observations for a reliable low-vs-moderate wind split."

    d["band"] = np.where(d["wind_speed"] <= 7, "low", "moderate")
    med = d.groupby("band")["pm2_5"].median()
    low_med = float(med.get("low", np.nan))
    mod_med = float(med.get("moderate", np.nan))

    # directional persistence under moderate wind
    mod = d[d["band"] == "moderate"].groupby("wind_cardinal")["pm2_5"].median()
    if not mod.empty:
        mod_ratio = float(mod.max() / (mod.median() + 1e-9))
    else:
        mod_ratio = 1.0

    if np.isfinite(low_med) and np.isfinite(mod_med):
        if low_med > mod_med * 1.10 and mod_ratio < 1.15:
            return "Interpretation: Low-wind PM is broadly higher across directions → stagnation/trapping is a key smog driver."
        if mod_ratio > 1.25:
            top = mod.idxmax()
            return f"Interpretation: Under moderate wind, PM spikes mainly from {top} → transport from that upwind sector is likely."
        if mod_med > low_med * 1.10:
            return "Interpretation: Moderate wind has higher PM than low wind → wind may be importing pollution (advection dominates)."
        return "Interpretation: Mixed result → both local accumulation and some directional transport may be contributing."
    return "Interpretation: Not enough stable low/moderate wind data to conclude."

def outcome_4_ratio_wind_frp(ratio_df: pd.DataFrame, fire_col: str):
    # PM2.5/PM10 ratio vs wind, FRP color
    d = ratio_df.dropna(subset=["wind_speed", "pm_ratio", fire_col]).copy()
    if len(d) < 20:
        return "Interpretation: Not enough observations to reliably link ratio, wind, and FRP."

    corr_fire = float(d["pm_ratio"].corr(d[fire_col], method="spearman"))
    corr_wind = float(d["pm_ratio"].corr(d["wind_speed"], method="spearman"))

    low_mask, high_mask = _banded(d[fire_col], 0.75)
    if low_mask is None:
        return "Interpretation: Not enough FRP variation to infer a fire–ratio link."

    r_low = float(d.loc[low_mask, "pm_ratio"].median())
    r_high = float(d.loc[high_mask, "pm_ratio"].median())
    delta = r_high - r_low

    if delta > 0.03 and corr_fire > 0.15:
        return "Interpretation: Higher FRP aligns with higher PM2.5/PM10 ratio → fires likely contribute fine smoke-dominated particles."
    if corr_wind < -0.15:
        return "Interpretation: Ratio decreases with wind speed → coarse dust influence may rise with wind and/or fine smoke disperses faster."
    if corr_wind > 0.15:
        return "Interpretation: Ratio increases with wind speed → wind may be importing fine regional haze (transport)."
    if abs(corr_fire) < 0.10:
        return "Interpretation: Ratio remains weakly linked to FRP → PM2.5 dominance may be non-fire sources or transported smoke not captured by local FRP."
    return "Interpretation: Mixed result → ratio suggests shifting particle mix with modest fire signal."

def outcome_5_fire_lag(daily: pd.DataFrame):
    # Fire lag test: strongest lag
    if daily.empty:
        return "Interpretation: Not enough daily data to infer lag timing."

    def corr(a, b):
        tmp = daily[[a, b]].dropna()
        if len(tmp) < 12:
            return None
        return float(tmp[a].corr(tmp[b]))

    c0 = corr("fire_lag0", "pm2_5")
    c1 = corr("fire_lag1", "pm2_5")
    c2 = corr("fire_lag2", "pm2_5")

    vals = {"Lag 0": c0, "Lag 1": c1, "Lag 2": c2}
    vals = {k: v for k, v in vals.items() if v is not None}
    if not vals:
        return "Interpretation: Not enough valid overlap after lagging to evaluate lag timing."

    best = max(vals, key=lambda k: vals[k])
    best_val = vals[best]

    if best_val < 0.15:
        return "Interpretation: All lags are weak/flat → local FRP does not explain PM well; other sources or meteorology likely dominate."
    if best == "Lag 0":
        return "Interpretation: Lag 0 is strongest → same-day burning impacts PM quickly."
    if best == "Lag 1":
        return "Interpretation: Lag 1 is strongest → next-day PM response suggests transport/overnight accumulation/chemistry."
    return "Interpretation: Lag 2 is strongest → longer-range transport or secondary PM formation likely dominates."

DISTRICT_CENTROIDS = {k: (v["lat"], v["lon"]) for k, v in DISTRICTS.items()}

CARDINAL_TO_DEG = {
    "N": 0, "NE": 45, "E": 90, "SE": 135,
    "S": 180, "SW": 225, "W": 270, "NW": 315
}

def km_to_lat(km: float) -> float:
    return km / 111.0

def km_to_lon(km: float, lat_deg: float) -> float:
    return km / (111.0 * max(0.15, math.cos(math.radians(lat_deg))))

def destination_point(lat: float, lon: float, bearing_deg: float, distance_km: float) -> tuple[float, float]:
    # Small-distance approximation (good for ~0–200km)
    dlat = km_to_lat(distance_km) * math.cos(math.radians(bearing_deg))
    dlon = km_to_lon(distance_km, lat) * math.sin(math.radians(bearing_deg))
    return (lat + dlat, lon + dlon)

def make_sector_polygon(lat: float, lon: float, start_bearing: float, end_bearing: float, radius_km: float, steps: int = 18):
    """
    Builds a wedge (sector) polygon centered at (lat, lon).
    Returns lists: (lats, lons) suitable for scattermapbox with fill="toself".
    """
    # Ensure clockwise sweep
    if end_bearing < start_bearing:
        end_bearing += 360

    bearings = [start_bearing + i * (end_bearing - start_bearing) / steps for i in range(steps + 1)]
    arc_pts = [destination_point(lat, lon, b % 360, radius_km) for b in bearings]

    poly = [(lat, lon)] + arc_pts + [(lat, lon)]
    lats = [p[0] for p in poly]
    lons = [p[1] for p in poly]
    return lats, lons

def hover_info_block(key_prefix: str, params_html: str, working_html: str):
    # key_prefix is just to keep uniqueness; not used by CSS but good practice
    st.markdown(f"""
    <div class="hover-info-row" id="{key_prefix}">
      <div class="hover-btn">
        Parameters
        <div class="hover-pop">{params_html}</div>
      </div>

      <div class="hover-btn">
        Working
        <div class="hover-pop">{working_html}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

PLOTLY_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtons": [["toImage", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"]],
    "scrollZoom": True,
    "doubleClick": "reset",  # double-click resets zoom
}

PANEL_H = 400  # pick 360–420; 380 is a good balanced dashboard height
PANEL_MARGIN = dict(l=10, r=10, t=45, b=10)

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

# --- GRAPH BUTTON CINFIG ---


# --- UX POLISH (Transitions + Seamless Reruns) ---
def inject_global_ux_css():
    st.markdown(
        """
        <style>
        /* Smooth scrolling */
        html { scroll-behavior: smooth; }

        /* Subtle page fade-in on each rerun */
        section.main > div {
            animation: fadeIn 260ms ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(4px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        /* Reduce visual jitter by keeping spacing consistent */
        .block-container {
            padding-top: 1.25rem !important;
            padding-bottom: 2rem !important;
        }

        /* Metrics: card feel + hover */
        div[data-testid="stMetric"] {
            border: 1px solid rgba(49, 51, 63, 0.12);
            border-radius: 12px;
            padding: 12px 14px;
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 24px rgba(0,0,0,0.08);
            border-color: rgba(49, 51, 63, 0.20);
        }

        /* Plotly charts: fade-in + gentle hover */
        div[data-testid="stPlotlyChart"] {
            border-radius: 12px;
            overflow: hidden;
            transition: transform 160ms ease, box-shadow 160ms ease;
            animation: chartFade 260ms ease-out;
        }
        @keyframes chartFade {
            from { opacity: 0; transform: translateY(6px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        div[data-testid="stPlotlyChart"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 24px rgba(0,0,0,0.08);
        }

        div[data-testid="stPlotlyChart"] {
        border-radius: 16px !important;
        overflow: hidden !important;
        }

        /* Expanders: smoother open/close feel */
        details[data-testid="stExpander"] {
            border-radius: 12px;
            border: 1px solid rgba(49, 51, 63, 0.12);
            padding: 6px 10px;
            transition: border-color 160ms ease, box-shadow 160ms ease;
        }
        details[data-testid="stExpander"]:hover {
            border-color: rgba(49, 51, 63, 0.20);
            box-shadow: 0 10px 24px rgba(0,0,0,0.06);
        }

        /* Inputs: smoother focus */
        div[data-testid="stSelectbox"] label,
        div[data-testid="stDateInput"] label {
            transition: opacity 160ms ease;
        }
        div[data-testid="stSelectbox"]:focus-within,
        div[data-testid="stDateInput"]:focus-within {
            animation: focusPop 140ms ease-out;
        }
        @keyframes focusPop {
            from { transform: scale(0.997); }
            to   { transform: scale(1.0); }
        }

        /* Dividers: soften */
        hr {
            opacity: 0.45;
        }

        /* --- Cursor fix: selectboxes should not show I-beam --- */
        div[data-testid="stSelectbox"] * {
        cursor: pointer !important;
        }

        /* Keep text cursor only where typing is expected */
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stNumberInput"] input {
        cursor: text !important;
        }

        /* Dropdown list items should also be pointer */
        div[role="listbox"] * {
        cursor: pointer !important;
        }

        div[data-testid="stPlotlyChart"],
        div[data-testid="stPlotlyChart"] > div,
        div[data-testid="stPlotlyChart"] .js-plotly-plot,
        div[data-testid="stPlotlyChart"] .plot-container,
        div[data-testid="stPlotlyChart"] .svg-container,
        div[data-testid="stPlotlyChart"] .main-svg,
        div[data-testid="stPlotlyChart"] canvas {
        border-radius: 16px !important;
        overflow: hidden !important;
        }
       
        </style>
        """,
        unsafe_allow_html=True,
    )

st.markdown("""
<style>
/* Container holding the two hover buttons */
.hover-info-row{
  display:flex;
  gap:12px;
  align-items:center;
  margin-top:6px;
  margin-bottom:6px;
}

/* Pill button */
.hover-btn{
  position:relative;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:6px 12px;
  font-size:12px;
  line-height:1;
  border-radius:999px; /* 50% rounded */
  border:1px solid rgba(255,255,255,0.18);
  background:rgba(255,255,255,0.06);
  color:rgba(255,255,255,0.92);
  cursor:pointer;
  user-select:none;
  transition:background 120ms ease, border-color 120ms ease, transform 120ms ease;
}

.hover-btn:hover{
  background:rgba(255,255,255,0.10);
  border-color:rgba(255,255,255,0.28);
  transform:translateY(-1px);
}

/* Bubble popover (hidden by default) */
.hover-pop{
  position:absolute;
  left:0;
  top:110%;
  width:360px;
  max-width:70vw;
  padding:10px 12px;
  border-radius:14px;
  background:#141820; !important;
  border:1px solid rgba(255,255,255,0.12);
  box-shadow:0 10px 30px rgba(0,0,0,0.45);
  color:rgba(255,255,255,0.92);
  font-size:12px;

  opacity:1;
  visibility:hidden;
  transform:translateY(-4px);
  transition:opacity 120ms ease, transform 120ms ease, visibility 120ms ease;
  z-index:9999;
}

/* Small tail like a chat bubble */
.hover-pop:before{
  content:"";
  position:absolute;
  top:-7px;
  left:18px;
  width:12px;
  height:12px;
  background:#141820; !important;
  border-left:1px solid rgba(255,255,255,0.12);
  border-top:1px solid rgba(255,255,255,0.12);
  transform:rotate(45deg);
}

/* Show popover only when hovering over the button */
.hover-btn:hover .hover-pop{
  opacity:1;
  visibility:visible;
  transform:translateY(0);
}

/* Bigger interpretation text */
.interpretation-note{
  margin-top:6px; !important;
  margin-buttom:20px; !important;
  font-size:14px; !important;
  line-height:1.35; !important;
  color:rgba(255,255,255,0.85); !important;
}
</style>
""", unsafe_allow_html=True)

def persist_scroll_position_across_reruns():
    components.html(
        """
        <script>
        (function() {
          const key = "psip_scrollY";
          const y = Number(localStorage.getItem(key) || "0");
          if (!Number.isNaN(y) && y > 0) {
            setTimeout(() => window.scrollTo(0, y), 60);
          }
          window.addEventListener("beforeunload", () => {
            localStorage.setItem(key, String(window.scrollY || 0));
          });
        })();
        </script>
        """,
        height=0,
    )

inject_global_ux_css()
persist_scroll_position_across_reruns()

# --- HEADER ---
st.title("Punjab Smog Intelligence Platform")
st.markdown("Real-time pollution monitoring & historic analysis.")
st.divider()

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db_connection():
    db_url = st.secrets["connections"]["db_url"]
    return create_engine(db_url)

# ==========================================
# 1. GLOBAL CONTROLS (Top of Page)
# ==========================================
f1, f2 = st.columns([1, 3])

with f1:
    st.markdown("**Select Time Range:**")
    time_option = st.selectbox(
        "Time Range",
        [
            "Last 24 Hours",
            "Last 7 Days",
            "Last 30 Days",
            "Last 6 Months",
            "Last 1 Year",
            "Custom Range",
            "Specific Date",
        ],
        label_visibility="collapsed",
        key="time_option",
    )

    # This placeholder makes the “new box” appear in the same place, seamlessly
    time_detail = st.container()

# --- TIME LOGIC ---
end_date = datetime.now()
start_date = end_date - timedelta(hours=24)

if time_option == "Last 7 Days":
    start_date = end_date - timedelta(days=7)

elif time_option == "Last 30 Days":
    start_date = end_date - timedelta(days=30)

elif time_option == "Last 6 Months":
    start_date = end_date - timedelta(days=180)

elif time_option == "Last 1 Year":
    start_date = end_date - timedelta(days=365)

elif time_option == "Custom Range":
    # “New box” appears under the dropdown seamlessly
    with time_detail:
        c_col1, c_col2 = st.columns(2)
        c_start = c_col1.date_input(
            "Start Date",
            value=(end_date - timedelta(days=7)).date(),
            key="custom_start_date",
        )
        c_end = c_col2.date_input(
            "End Date",
            value=end_date.date(),
            key="custom_end_date",
        )
        start_date = datetime.combine(c_start, datetime.min.time())
        end_date = datetime.combine(c_end, datetime.max.time())

elif time_option == "Specific Date":
    # “New box” appears under the dropdown seamlessly
    with time_detail:
        spec_date = st.date_input(
            "Select Date",
            value=end_date.date(),
            key="specific_date",
        )
        start_date = datetime.combine(spec_date, datetime.min.time())
        end_date = datetime.combine(spec_date, datetime.max.time())

# --- LOAD DATA ---
def load_data(start, end):
    engine = get_db_connection()
    query = text("""
        SELECT * FROM smog_metrics 
        WHERE timestamp BETWEEN :start AND :end
        ORDER BY timestamp DESC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"start": start, "end": end})
    return df

def add_wind_cardinals(df):
    if df.empty: 
        return df
    bins = [0, 45, 90, 135, 180, 225, 270, 315, 360]
    labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    df['wind_cardinal'] = pd.cut(df['wind_dir'], bins=bins, labels=labels, include_lowest=True)
    return df

# --- MAIN DASHBOARD ---
try:
    with st.spinner(f"Loading data..."):
        df = load_data(start_date, end_date)
        df = add_wind_cardinals(df)

    if not df.empty:
        latest_ts = df['timestamp'].max()
        latest_df = df[df['timestamp'] == latest_ts]

        # ==========================================
        # PART 1: GLOBAL MONITORING
        # ==========================================

        # --- TOP STATS ---
        worst_row = latest_df.loc[latest_df['pm2_5'].idxmax()]

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Most Polluted", f"{worst_row['district']}", f"{worst_row['pm2_5']:.0f} PM2.5", delta_color="inverse")
        m2.metric("Avg PM2.5", f"{latest_df['pm2_5'].mean():.0f} µg/m³")
        m3.metric("Avg PM10", f"{latest_df['pm10'].mean():.0f} µg/m³")
        m4.metric("Avg Fire Intensity", f"{latest_df['provincial_fire_load'].iloc[0]:.0f} MW")
        m5.metric("Last Updated", str(latest_ts))

        st.divider()

        # --- CHARTS ---
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Top 10 Polluted Districts")
            top_10 = latest_df.nlargest(10, "pm2_5")[["district", "pm2_5", "pm10"]].copy()

            # Keep district order strictly by PM2.5 (descending)
            top_10["district"] = pd.Categorical(
                top_10["district"],
                categories=top_10.sort_values("pm2_5", ascending=True)["district"].tolist(),
                ordered=True,
            )

            top_10_melt = top_10.melt(
                id_vars="district",
                value_vars=["pm2_5", "pm10"],
                var_name="Pollutant",
                value_name="Value",
            )

            fig_bar = px.bar(
                top_10_melt,
                x="Value",
                y="district",
                orientation="h",
                color="Pollutant",
                barmode="group",
                text=top_10_melt["Value"].round(0).astype(int),
                color_discrete_map={"pm2_5": "#FF4B4B", "pm10": "#FFA500"},
            )

            fig_bar.update_traces(textposition="outside", cliponaxis=False)
            fig_bar.update_layout(
                yaxis={
                    "categoryorder": "array",
                    "categoryarray": top_10.sort_values("pm2_5", ascending=True)["district"].tolist()
                },
                xaxis_title="µg/m³",
                legend_title_text="",
                margin=dict(l=10, r=10, t=10, b=10),
            )

            st.plotly_chart(fig_bar, use_container_width=True, config=PLOTLY_CONFIG)

            # --- INFO NOTE ---
            st.caption("""
            **Role in Smog Analysis:** Identifies current "Hotspots." 
            This helps authorities prioritize emergency measures (like school closures or lockdowns) in the most affected districts.
            """)

        with c2:
            st.subheader("Trend Comparison")

            fixed = ['Islamabad', 'Lahore', 'Multan', 'Faisalabad', 'Gujranwala', 'Sargodha']
            top_2 = latest_df.nlargest(2, 'pm2_5')['district'].tolist()
            final_list = list(set(fixed + top_2))

            trend_data = df[df['district'].isin(final_list)]

            fig_line = px.line(
                trend_data,
                x='timestamp', y='pm2_5',
                color='district',
                markers=True,
                title=f"Comparison: Major Cities + {', '.join(top_2)}"
            )
            st.plotly_chart(fig_line, use_container_width=True, config=PLOTLY_CONFIG)

            # --- INFO NOTE ---
            st.caption("""
            **Role in Smog Analysis:** Tracks the "Persistence" of smog.
            If the line stays flat and high, it means smog is trapped (Stagnation). If it dips during the day, it indicates ventilation.
            """)

        st.divider()

        # ==========================================
        # PART 2: SMOG DIAGNOSTICS (Deep Dive)
        # ==========================================
        st.header("Smog Diagnostics")

        d_col1, d_col2 = st.columns([1, 3])
        with d_col1:
            st.markdown("**Select District to Analyze:**")
            districts = sorted(df["district"].unique())

            # PM2.5 snapshot at the latest timestamp (used to annotate dropdown labels)
            pm25_by_district = (
                latest_df.groupby("district")["pm2_5"].mean().to_dict()
            )

            # Most polluted district right now (already computed as worst_row above)
            worst_district = str(worst_row["district"])

            # Default selection logic:
            # - On first load, default to worst_district
            # - On later reruns, keep user selection unless it becomes invalid
            if "selected_city" not in st.session_state or st.session_state["selected_city"] not in districts:
                st.session_state["selected_city"] = worst_district if worst_district in districts else districts[0]

            def district_label(d):
                v = pm25_by_district.get(d, None)
                if v is None or pd.isna(v):
                    return f"{d}   (PM2.5 - NULL)"
                return f"{d}   (PM2.5 - {v:.0f})"

            selected_city = st.selectbox(
                "District",
                options=districts,
                index=districts.index(st.session_state["selected_city"]),
                format_func=district_label,
                label_visibility="collapsed",
                key="selected_city",
            )

        city_df = df[df['district'] == selected_city]

        if not city_df.empty:
            g1, g2 = st.columns(2)

            with g1:
                st.markdown(f"**Wind Impact ({selected_city})**")

                # Plot both PM2.5 and PM10 against wind_speed on the same Y-axis scale
                scatter_df = (
                    city_df[["wind_speed", "pm2_5", "pm10"]]
                    .melt(
                        id_vars="wind_speed",
                        value_vars=["pm2_5", "pm10"],
                        var_name="Pollutant",
                        value_name="Concentration",
                    )
                    .dropna(subset=["wind_speed", "Concentration"])
                )

                fig_scatter = px.scatter(
                    scatter_df,
                    x="wind_speed",
                    y="Concentration",
                    color="Pollutant",
                    symbol="Pollutant",
                    trendline="ols",
                    opacity=0.70,
                    color_discrete_map={"pm2_5": "#FF4B4B", "pm10": "#FFA500"},
                    title=f"Wind Speed vs PM2.5 / PM10 in {selected_city}",
                    labels={"wind_speed": "Wind Speed", "Concentration": "Concentration (µg/m³)", "Pollutant": ""},
                )
                fig_scatter.update_traces(marker=dict(size=10))
                fig_scatter.update_layout(height=PANEL_H, margin=PANEL_MARGIN, dragmode=False)

                st.plotly_chart(fig_scatter, use_container_width=True, config=PLOTLY_CONFIG)

                hover_info_block(
                    "diag_1_scatter",
                    params_html="""
                    <b>Parameters of the graph</b><br>
                    • <b>X:</b> Wind Speed (m/s or km/h)<br>
                    • <b>Y:</b> PM2.5 and PM10 concentration (µg/m³)<br>
                    • <b>Marks:</b> points (observations)<br>
                    • <b>Lines:</b> fitted trend lines for PM2.5 and PM10
                    """,
                    working_html="""
                    <b>Working of the graph</b><br>
                    • Plots how PM changes as wind speed changes.<br>
                    • Trend line summarizes the average relationship (dispersion effect).<br>
                    • Used to infer whether air is “stagnant” (high PM) vs “ventilated” (low PM).
                    """,
                )

                st.markdown(
                    f"<div class='interpretation-note'>{outcome_1_wind_speed_pm(city_df)}</div>",
                    unsafe_allow_html=True
                )

                # ==========================================
                # Wind Direction vs Median PM2.5 (single panel)
                # Color/series = wind band (Low vs Moderate)
                # ==========================================

                if "wind_cardinal" not in city_df.columns:
                    city_df = add_wind_cardinals(city_df)

                wind_dir_order = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                wind_band_order = ["Low (≤7 km/h)", "Moderate (>7 km/h)"]

                wd_df = city_df[["wind_cardinal", "wind_speed", "pm2_5"]].dropna(subset=["wind_cardinal", "wind_speed", "pm2_5"]).copy()

                wd_df["Wind Band"] = wd_df["wind_speed"].apply(lambda v: wind_band_order[0] if v <= 7 else wind_band_order[1])
                wd_df["Wind Band"] = pd.Categorical(wd_df["Wind Band"], categories=wind_band_order, ordered=True)
                wd_df["wind_cardinal"] = pd.Categorical(wd_df["wind_cardinal"], categories=wind_dir_order, ordered=True)

                wind_pm_median = (
                    wd_df.groupby(["wind_cardinal", "Wind Band"], observed=False, as_index=False)["pm2_5"]
                    .median()
                    .rename(columns={"pm2_5": "Median PM2.5"})
                )

                # Ensure both bands appear for every direction (even if missing in data)
                full = pd.MultiIndex.from_product([wind_dir_order, wind_band_order], names=["wind_cardinal", "Wind Band"]).to_frame(index=False)
                plot_df = full.merge(wind_pm_median, on=["wind_cardinal", "Wind Band"], how="left")

                fig_wind_pm = px.bar(
                    plot_df,
                    x="wind_cardinal",
                    y="Median PM2.5",
                    color="Wind Band",
                    barmode="group",
                    category_orders={"wind_cardinal": wind_dir_order, "Wind Band": wind_band_order},
                    color_discrete_map={"Low (≤7 km/h)": "#6EA8FF", "Moderate (>7 km/h)": "#FFD166"},
                    title=f"Wind Direction vs Median PM2.5 by Wind Speed — {selected_city}",
                    labels={"wind_cardinal": "Wind Direction", "Median PM2.5": "Median PM2.5 (µg/m³)", "Wind Band": ""},
                )

                fig_wind_pm.update_layout(height=PANEL_H, margin=PANEL_MARGIN, dragmode=False)
                st.plotly_chart(fig_wind_pm, use_container_width=True, config=PLOTLY_CONFIG)

                hover_info_block(
                    "diag_3_dir_split",
                    params_html="""
                    <b>Parameters of the graph</b><br>
                    • <b>X:</b> Wind direction bins (N, NE, E, SE, S, SW, W, NW)<br>
                    • <b>Y:</b> Median PM2.5 (µg/m³)<br>
                    • <b>Series:</b> two categories by wind speed (Low vs Moderate)
                    """,
                    working_html="""
                    <b>Working of the graph</b><br>
                    • For each direction bin, compute median PM2.5 separately for low-wind vs moderate-wind.<br>
                    • Tests whether direction effects persist when air is moving vs just stagnating.
                    """,
                )

                st.markdown(
                    f"<div class='interpretation-note'>{outcome_3_dir_split_wind(city_df)}</div>",
                    unsafe_allow_html=True
                )

            with g2:
                st.markdown(f"**Pollution Source ({selected_city})**")
                rose_data = city_df.groupby('wind_cardinal')[['pm2_5', 'pm10']].mean().reset_index()
                rose_melted = rose_data.melt(id_vars='wind_cardinal', var_name='Pollutant', value_name='Concentration')

                fig_rose = px.bar_polar(
                    rose_melted,
                    r="Concentration", theta="wind_cardinal",
                    color="Pollutant",
                    template="plotly_dark",
                    color_discrete_map={"pm2_5": "#FF4B4B", "pm10": "#FFA500"},
                    title=f"Avg Pollution by Wind Direction"
                )
                
                # ----------------------------
                # Map-based Wind Rose (Dark Map) — refined
                # - No direction labels in legend
                # - Compass overlay
                # - PM2.5 / PM10 colored sectors + legend
                # - Higher contrast boundaries/text
                # - Rounded corners handled by CSS (overflow hidden + border radius)
                # ----------------------------
                if selected_city not in DISTRICT_CENTROIDS:
                    st.caption("Map overlay not available (missing district coordinates).")
                else:
                    src_lat, src_lon = DISTRICT_CENTROIDS[selected_city]

                    dir_order = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                    rose_data_ordered = rose_data.set_index("wind_cardinal").reindex(dir_order).reset_index()

                    # Scale separately for PM2.5 and PM10
                    pm25_vals = rose_data_ordered["pm2_5"].fillna(0).astype(float)
                    pm10_vals = rose_data_ordered["pm10"].fillna(0).astype(float)
                    pm25_max = float(pm25_vals.max()) if float(pm25_vals.max()) > 0 else 1.0
                    pm10_max = float(pm10_vals.max()) if float(pm10_vals.max()) > 0 else 1.0

                    # Colors to match your polar chart
                    PM25_COLOR = "#FF4B4B"
                    PM10_COLOR = "#FFA500"

                    # Base map (dark) + high contrast text
                    fig_map_rose = px.scatter_mapbox(
                        lat=[src_lat],
                        lon=[src_lon],
                        zoom=7,
                        height=PANEL_H,
                        title=f"Downwind Impact Sectors — {selected_city}"
                    )
                    fig_map_rose.update_layout(

                    mapbox_style="white-bg",
                    mapbox_layers=[
                        {
                            "below": "traces",
                            "sourcetype": "raster",
                            "source": ["https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"],
                            "sourceattribution": "© OpenStreetMap © CARTO",
                        }
                    ],
                    margin=dict(l=0, r=0, t=45, b=0),

                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="rgba(255,255,255,0.92)"),
                        title_font=dict(color="rgba(255,255,255,0.96)"),
                        legend=dict(
                            orientation="h",
                            x=0.02, y=0.98,              # inside the frame
                            xanchor="left", yanchor="top",
                            bgcolor="rgba(0,0,0,0.45)",
                            bordercolor="rgba(255,255,255,0.24)",
                            borderwidth=1,
                            font=dict(color="rgba(255,255,255,0.95)"),
                        ),
                        dragmode=False,  # consistent with your “no zoom/crop” preference
                    )

                    # Sector sizing
                    base_km = 12
                    max_add_km = 90

                    # Legend toggles (show PM2.5/PM10 once)
                    shown_pm25_legend = False
                    shown_pm10_legend = False

                    for _, row in rose_data_ordered.iterrows():
                        d = row["wind_cardinal"]
                        if pd.isna(d):
                            continue

                        bearing_center = CARDINAL_TO_DEG.get(str(d))
                        if bearing_center is None:
                            continue

                        pm25 = float(row["pm2_5"]) if pd.notna(row["pm2_5"]) else 0.0
                        pm10 = float(row["pm10"]) if pd.notna(row["pm10"]) else 0.0

                        # Separate radii so both pollutants are visible
                        r25 = base_km + (pm25 / pm25_max) * max_add_km
                        r10 = base_km + (pm10 / pm10_max) * max_add_km

                        # 45° bin => +/- 22.5°
                        start_b = (bearing_center - 22.5) % 360
                        end_b = (bearing_center + 22.5) % 360

                        # Draw PM10 first (typically larger), then PM2.5 on top
                        # --- PM10 sector ---
                        lats10, lons10 = make_sector_polygon(src_lat, src_lon, start_b, end_b, r10, steps=18)
                        fig_map_rose.add_trace(
                            dict(
                                type="scattermapbox",
                                lat=lats10,
                                lon=lons10,
                                mode="lines",
                                fill="toself",
                                legendgroup="pm10",
                                name="pm10",
                                showlegend=(not shown_pm10_legend),
                                hovertemplate=(
                                    f"<b>Direction</b>: {d}<br>"
                                    f"<b>PM10</b>: {pm10:.0f}<br>"
                                    f"<b>Radius</b>: {r10:.0f} km"
                                    "<extra></extra>"
                                ),
                                line=dict(width=2, color="rgba(255,165,0,1.0)"),  # high-contrast boundary
                                fillcolor="rgba(255,165,0,0.18)",
                            )
                        )
                        shown_pm10_legend = True

                        # --- PM2.5 sector ---
                        lats25, lons25 = make_sector_polygon(src_lat, src_lon, start_b, end_b, r25, steps=18)
                        fig_map_rose.add_trace(
                            dict(
                                type="scattermapbox",
                                lat=lats25,
                                lon=lons25,
                                mode="lines",
                                fill="toself",
                                legendgroup="pm25",
                                name="pm2_5",
                                showlegend=(not shown_pm25_legend),
                                hovertemplate=(
                                    f"<b>Direction</b>: {d}<br>"
                                    f"<b>PM2.5</b>: {pm25:.0f}<br>"
                                    f"<b>Radius</b>: {r25:.0f} km"
                                    "<extra></extra>"
                                ),
                                line=dict(width=2, color="rgba(255,75,75,1.0)"),
                                fillcolor="rgba(255,75,75,0.22)",
                            )
                        )
                        shown_pm25_legend = True

                    # Source marker
                    fig_map_rose.add_trace(
                        dict(
                            type="scattermapbox",
                            lat=[src_lat],
                            lon=[src_lon],
                            mode="markers",
                            name="Selected District",
                            showlegend=False,
                            marker=dict(size=12, color="rgba(255,255,255,0.95)"),
                            hovertemplate=f"<b>{selected_city}</b><extra></extra>"
                        )
                    )

                    # ----------------------------
                    # District labels (high-contrast, bold-like) — ADD THIS LAST
                    # ----------------------------
                    src_lat, src_lon = DISTRICT_CENTROIDS[selected_city]

                    # Show selected + nearest N districts to avoid clutter
                    def _haversine_km(lat1, lon1, lat2, lon2):
                        import math
                        R = 6371.0
                        p1, p2 = math.radians(lat1), math.radians(lat2)
                        dphi = math.radians(lat2 - lat1)
                        dl = math.radians(lon2 - lon1)
                        a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
                        return 2*R*math.asin(math.sqrt(a))

                    nearest = []
                    for name, (lat, lon) in DISTRICT_CENTROIDS.items():
                        d = _haversine_km(src_lat, src_lon, lat, lon)
                        nearest.append((d, name, lat, lon))

                    nearest.sort(key=lambda x: x[0])

                    # Keep: selected district + next 12 nearest
                    keep = []
                    for d, name, lat, lon in nearest:
                        if name == selected_city:
                            keep.insert(0, (name, lat, lon))
                        else:
                            keep.append((name, lat, lon))
                    keep = keep[:13]  # 1 (selected) + 12 nearest

                    names = [x[0] for x in keep]
                    lats  = [x[1] for x in keep]
                    lons  = [x[2] for x in keep]

                    # Shadow layer (creates "bold" effect)
                    fig_map_rose.add_trace(
                        dict(
                            type="scattermapbox",
                            lat=lats,
                            lon=lons,
                            mode="markers+text",
                            text=names,
                            textposition="top center",
                            textfont=dict(size=13, color="rgba(0,0,0,0.95)"),
                            marker=dict(size=2, color="rgba(0,0,0,0.01)"),  # invisible anchor
                            showlegend=False,
                            hoverinfo="skip",
                        )
                    )

                    # Foreground layer (main readable label)
                    fig_map_rose.add_trace(
                        dict(
                            type="scattermapbox",
                            lat=lats,
                            lon=lons,
                            mode="markers+text",
                            text=names,
                            textposition="top center",
                            textfont=dict(size=12, color="rgba(255,255,255,0.98)"),
                            marker=dict(size=2, color="rgba(255,255,255,0.01)"),  # invisible anchor
                            showlegend=False,
                            hoverinfo="skip",
                        )
                    )

                    # --- Compact, side-by-side layout (polar + map) ---
                    fig_rose.update_layout(height=PANEL_H, margin=dict(l=10, r=10, t=45, b=10))
                    fig_map_rose.update_layout(height=PANEL_H, margin=dict(l=0, r=0, t=45, b=0))

                    left, right = st.columns([1, 1.35], gap="small")  # map gets a bit more width

                    with left:
                        st.plotly_chart(fig_rose, use_container_width=True, config=PLOTLY_CONFIG)

                    fig_map_rose.update_layout(mapbox=dict(center=dict(lat=src_lat, lon=src_lon), zoom=6.2))
                    with right:
                        st.plotly_chart(fig_map_rose, use_container_width=True, config=PLOTLY_CONFIG)

                    hover_info_block(
                        "diag_2_rose_map",
                        params_html="""
                        <b>Parameters of the graph</b><br><br>
                        <b>Wind rose</b><br>
                        • <b>Direction bins:</b> N, NE, E, SE, S, SW, W, NW<br>
                        • <b>Radial value:</b> mean/median PM2.5 and PM10 (µg/m³)<br><br>
                        <b>Map</b><br>
                        • <b>Center:</b> target district<br>
                        • <b>Highlighted sectors:</b> directions associated with higher PM
                        """,
                        working_html="""
                        <b>Working of the graph</b><br>
                        • Wind rose groups observations by wind direction and computes average PM per direction.<br>
                        • Map visualizes those “dirty direction bins” as corridors to interpret likely source regions.
                        """,
                    )

                    st.markdown(
                        f"<div class='interpretation-note'>{outcome_2_wind_rose_map(city_df)}</div>",
                        unsafe_allow_html=True
                    )

                # ==========================================
                # Ratio Analysis: (PM2.5 / PM10) vs Wind, colored by Fire (local_fire_frp)
                # ==========================================

                fire_col = "local_fire_frp"

                if fire_col not in df.columns:
                    st.warning("Column 'local_fire_frp' not found in your data.")
                else:
                    ratio_df = city_df[["wind_speed", "pm2_5", "pm10", fire_col]].copy()

                    # Avoid divide-by-zero and invalid ratios
                    ratio_df = ratio_df.dropna(subset=["wind_speed", "pm2_5", "pm10", fire_col])
                    ratio_df = ratio_df[ratio_df["pm10"] > 0]

                    ratio_df["pm_ratio"] = ratio_df["pm2_5"] / ratio_df["pm10"]

                    # Optional: cap extreme ratios for readability (comment out if you want raw)
                    ratio_df = ratio_df[(ratio_df["pm_ratio"] >= 0) & (ratio_df["pm_ratio"] <= 2.0)]

                    fig_ratio = px.scatter(
                        ratio_df,
                        x="wind_speed",
                        y="pm_ratio",
                        color=fire_col,
                        opacity=0.75,
                        trendline="ols",
                        template="plotly_dark",
                        labels={
                            "wind_speed": "Wind Speed (km/h)",
                            "pm_ratio": "PM2.5 / PM10",
                            fire_col: "Local Fire FRP",
                        },
                        title=f"PM2.5/PM10 Ratio vs Wind Speed (Fire Intensity = Color) — {selected_city}",
                        color_continuous_scale="Turbo",
                    )

                    fig_ratio.update_traces(marker=dict(size=10))
                    fig_ratio.update_layout(height=PANEL_H, dragmode=False, margin=dict(l=10, r=10, t=45, b=10))

                    st.plotly_chart(fig_ratio, use_container_width=True, config=PLOTLY_CONFIG)

                    hover_info_block(
                        "diag_4_ratio",
                        params_html="""
                        <b>Parameters of the graph</b><br>
                        • <b>X:</b> Wind speed<br>
                        • <b>Y:</b> Ratio R = PM2.5 / PM10<br>
                        • <b>Color scale:</b> Fire FRP (district-level)<br>
                        • <b>Optional:</b> trend line for ratio vs wind speed
                        """,
                        working_html="""
                        <b>Working of the graph</b><br>
                        • Ratio indicates particle “type mix”:<br>
                        &nbsp;&nbsp;– Higher ratio → fine particles dominate (smoke/combustion/secondary PM)<br>
                        &nbsp;&nbsp;– Lower ratio → coarse dust dominates<br>
                        • FRP color shows whether higher fire intensity aligns with fine-particle dominance.
                        """,
                    )

                    st.markdown(
                        f"<div class='interpretation-note'>{outcome_4_ratio_wind_frp(ratio_df, fire_col)}</div>",
                        unsafe_allow_html=True
                    )

            # ==========================================
            # Fire Lag Test (TRUE DAILY LAG):
            # PM2.5(day t) vs local_fire_frp(day t-k)
            # k = 0, 1, 2
            # ==========================================
            st.subheader("Fire Lag Test (PM2.5 vs Local Fire FRP) — True Daily Lag")

            fire_col = "local_fire_frp"

            if fire_col not in df.columns:
                st.warning("Column 'local_fire_frp' not found in your data.")
            else:
                base = df[["district", "timestamp", "pm2_5", fire_col]].dropna().copy()
                base["timestamp"] = pd.to_datetime(base["timestamp"])

                # Build a district-day dataset (robust even if raw data is hourly)
                base["date"] = base["timestamp"].dt.date

                daily = (
                    base.groupby(["district", "date"], as_index=False)
                        .agg(
                            pm2_5=("pm2_5", "median"),              # or "mean" if you prefer
                            fire=("local_fire_frp", "sum"),         # daily total FRP; can use "mean" if desired
                        )
                        .sort_values(["district", "date"])
                )

                # True lag by day (t-1 day, t-2 days)
                daily["fire_lag0"] = daily["fire"]
                daily["fire_lag1"] = daily.groupby("district")["fire"].shift(1)
                daily["fire_lag2"] = daily.groupby("district")["fire"].shift(2)

                # Convert to long form for plotting
                lag_long = daily.melt(
                    id_vars=["district", "date", "pm2_5"],
                    value_vars=["fire_lag0", "fire_lag1", "fire_lag2"],
                    var_name="Lag",
                    value_name="Fire",
                ).dropna(subset=["Fire", "pm2_5"])

                lag_map = {"fire_lag0": "Lag 0 (t)", "fire_lag1": "Lag 1 (t-1 day)", "fire_lag2": "Lag 2 (t-2 days)"}
                lag_long["Lag"] = lag_long["Lag"].map(lag_map)

                fig_fire_lag = px.scatter(
                    lag_long,
                    x="Fire",
                    y="pm2_5",
                    color="Lag",
                    trendline="ols",
                    opacity=0.70,
                    template="plotly_dark",
                    title="PM2.5(day t) vs Local Fire FRP(day t−k), k = 0/1/2",
                    labels={"Fire": "Daily local_fire_frp (lagged)", "pm2_5": "Daily PM2.5 (median, µg/m³)", "Lag": ""},
                    color_discrete_map={
                        "Lag 0 (t)": "#6EA8FF",
                        "Lag 1 (t-1 day)": "#FFD166",
                        "Lag 2 (t-2 days)": "#FF4B4B",
                    },
                )

                fig_fire_lag.update_traces(marker=dict(size=9))
                fig_fire_lag.update_layout(height=420, margin=dict(l=10, r=10, t=60, b=10), dragmode=False)

                st.plotly_chart(fig_fire_lag, use_container_width=True, config=PLOTLY_CONFIG)

                hover_info_block(
                    "diag_5_lag",
                    params_html="""
                    <b>Parameters of the graph</b><br>
                    • <b>X:</b> Fire FRP with lag (Fire(t), Fire(t−1), Fire(t−2))<br>
                    • <b>Y:</b> PM2.5 at time t<br>
                    • <b>Series/colors:</b> separate point sets per lag (0/1/2)<br>
                    • <b>Trend line:</b> per lag (recommended)
                    """,
                    working_html="""
                    <b>Working of the graph</b><br>
                    • Tests whether PM responds to fires immediately or after a delay.<br>
                    • Strongest relationship indicates likely timing of smoke impact:
                        same day vs next day vs two days later.
                    """,
                )

                st.markdown(
                    f"<div class='interpretation-note'>{outcome_5_fire_lag(daily)}</div>",
                    unsafe_allow_html=True
                )
            
            with st.expander(f"View Raw Data for {selected_city}"):
                st.dataframe(city_df)
        else:
            st.warning(f"No data for {selected_city}")

    else:
        st.warning("No data found for this time range.")

except Exception as e:
    st.error(f"Error: {e}")
