import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
from datetime import datetime, timedelta
import streamlit.components.v1 as components
import math
from locations import DISTRICTS

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

PLOTLY_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtons": [["toImage", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"]],
    "scrollZoom": True,
    "doubleClick": "reset",  # double-click resets zoom
}

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

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

        </style>
        """,
        unsafe_allow_html=True,
    )

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
            top_10 = latest_df.nlargest(10, 'pm2_5')

            fig_bar = px.bar(
                top_10,
                x='pm2_5', y='district',
                orientation='h',
                color='pm2_5', color_continuous_scale='Reds',
                text='pm2_5'
            )
            fig_bar.update_layout(yaxis={'categoryorder': 'total ascending'})
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
                fig_scatter = px.scatter(
                    city_df,
                    x="wind_speed", y="pm2_5",
                    color="pm2_5", color_continuous_scale="RdYlGn_r",
                    size="pm10",
                    trendline="ols",
                    title=f"Wind Speed vs PM2.5 in {selected_city}"
                )
                st.plotly_chart(fig_scatter, use_container_width=True, config=PLOTLY_CONFIG)

                # --- INFO NOTE ---
                st.caption("""
                **Role in Smog Analysis:** Measures "Dispersion Capacity."
                A downward trend line proves that higher wind speeds are successfully cleaning the air. If the line is flat, wind is ineffective.
                """)

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
                st.plotly_chart(fig_rose, use_container_width=True, config=PLOTLY_CONFIG)
                
                # ----------------------------
                # Map-based Wind Rose (Dark Map)
                # Shows affected geographic sectors + magnitude
                # ----------------------------
                if selected_city not in DISTRICT_CENTROIDS:
                    st.caption("Map overlay not available (missing district coordinates).")
                else:
                    src_lat, src_lon = DISTRICT_CENTROIDS[selected_city]

                    # Ensure consistent direction order
                    dir_order = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                    rose_data_ordered = rose_data.set_index("wind_cardinal").reindex(dir_order).reset_index()

                    # Choose which pollutant drives impact magnitude (PM2.5 is typical)
                    vals = rose_data_ordered["pm2_5"].fillna(0).astype(float)
                    v_max = float(vals.max()) if float(vals.max()) > 0 else 1.0

                    # Map styling: dark theme without needing tokens
                    fig_map_rose = px.scatter_mapbox(
                        lat=[src_lat],
                        lon=[src_lon],
                        zoom=7,
                        height=430,
                        title=f"Downwind Impact Sectors (PM2.5) — {selected_city}"
                    )
                    fig_map_rose.update_layout(
                        mapbox_style="carto-darkmatter",
                        margin=dict(l=0, r=0, t=40, b=0)
                    )

                    # Draw 8 sectors (each 45° wide, centered on cardinal direction)
                    # Sector radius scales with PM2.5 magnitude (shows "how much")
                    base_km = 15       # minimum visible radius
                    max_add_km = 85    # extra radius at max PM2.5

                    for _, row in rose_data_ordered.iterrows():
                        d = row["wind_cardinal"]
                        if pd.isna(d):
                            continue

                        bearing_center = CARDINAL_TO_DEG.get(str(d))
                        if bearing_center is None:
                            continue

                        pm25 = float(row["pm2_5"]) if pd.notna(row["pm2_5"]) else 0.0
                        pm10 = float(row["pm10"]) if pd.notna(row["pm10"]) else 0.0

                        # Scale radius by PM2.5
                        radius_km = base_km + (pm25 / v_max) * max_add_km

                        # Sector span: 45° bin => +/- 22.5°
                        start_b = (bearing_center - 22.5) % 360
                        end_b = (bearing_center + 22.5) % 360

                        lats, lons = make_sector_polygon(src_lat, src_lon, start_b, end_b, radius_km, steps=18)

                        # Opacity also reflects strength
                        opacity = 0.15 + 0.45 * (pm25 / v_max)

                        fig_map_rose.add_trace(
                            dict(
                                type="scattermapbox",
                                lat=lats,
                                lon=lons,
                                mode="lines",
                                fill="toself",
                                name=f"{d}",
                                hovertemplate=(
                                    f"<b>{d}</b><br>"
                                    f"PM2.5: {pm25:.0f}<br>"
                                    f"PM10: {pm10:.0f}<br>"
                                    f"Impact radius: {radius_km:.0f} km"
                                    "<extra></extra>"
                                ),
                                line=dict(width=1),
                                opacity=opacity,
                            )
                        )

                    # Source marker on top
                    fig_map_rose.add_trace(
                        dict(
                            type="scattermapbox",
                            lat=[src_lat],
                            lon=[src_lon],
                            mode="markers",
                            name="Selected District",
                            marker=dict(size=12),
                            hovertemplate=f"<b>{selected_city}</b><extra></extra>"
                        )
                    )

                    # Optional: disable drag zoom if you want (consistent with your earlier UX choice)
                    fig_map_rose.update_layout(dragmode=False)

                    st.plotly_chart(fig_map_rose, use_container_width=True, config=PLOTLY_CONFIG)


                # --- INFO NOTE ---
                st.caption("""
                **Role in Smog Analysis:** Identifies the "Source."
                Long bars indicate which direction the pollution is blowing from (e.g., East = Cross-border crop burning; West = Local vehicular emissions).
                """)

            with st.expander(f"View Raw Data for {selected_city}"):
                st.dataframe(city_df)
        else:
            st.warning(f"No data for {selected_city}")

    else:
        st.warning("No data found for this time range.")

except Exception as e:
    st.error(f"Error: {e}")
