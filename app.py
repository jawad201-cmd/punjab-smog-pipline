import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
from datetime import datetime, timedelta
import streamlit.components.v1 as components

# PLOTLY_CONFIG = {
#     "displayModeBar": True,
#     "displaylogo": False,
#     "modeBarButtons": [["toImage"]],  # only “Save image”
# }
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
                    return f"{d}  —  PM2.5: —"
                return f"{d}  —  PM2.5: {v:.0f}"

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
