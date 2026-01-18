import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

# --- HEADER ---
st.title("Punjab Smog Intelligence Platform")
st.markdown("Real-time pollution monitoring (PM2.5/PM10) combined with Wind Dynamics analysis.")
st.divider()

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db_connection():
    db_url = st.secrets["connections"]["db_url"]
    return create_engine(db_url)

# --- LOAD DATA ---
def load_data():
    engine = get_db_connection()
    # Fetch 2000 rows to ensure we have enough history for trendlines
    query = """
    SELECT * FROM smog_metrics 
    ORDER BY timestamp DESC 
    LIMIT 2000;
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

# --- HELPER: WIND CARDINALS ---
def add_wind_cardinals(df):
    bins = [0, 45, 90, 135, 180, 225, 270, 315, 360]
    labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    df['wind_cardinal'] = pd.cut(df['wind_dir'], bins=bins, labels=labels, include_lowest=True)
    return df

# --- MAIN DASHBOARD ---
try:
    with st.spinner("Syncing with Supabase Cloud..."):
        # 1. Load the "Global" Dataset (All cities)
        global_df = load_data()
        global_df = add_wind_cardinals(global_df)

    # ==========================================
    # SIDEBAR FILTER
    # ==========================================
    with st.sidebar:
        st.header("Controls")
        districts = sorted(global_df['district'].unique())
        districts.insert(0, "All Punjab")
        selected_city = st.selectbox("Select Region:", districts)
        st.caption(f"Analyzing: {selected_city}")
        st.divider()
        st.markdown("Created with **Python, Supabase & Streamlit**")

    # 2. Create the "Filtered" Dataset (Selected city only)
    if selected_city != "All Punjab":
        filtered_df = global_df[global_df['district'] == selected_city]
    else:
        filtered_df = global_df

    if not filtered_df.empty:
        # Get latest snapshot for KPIs
        latest_time = filtered_df['timestamp'].max()
        current_data = filtered_df[filtered_df['timestamp'] == latest_time]
        
        # Taking mean ensures if "All Punjab" is selected, we get province averages
        # If "Lahore" is selected, mean of 1 row is just that row's value.
        kpi_pm25 = current_data['pm2_5'].mean()
        kpi_pm10 = current_data['pm10'].mean()
        kpi_wind = current_data['wind_speed'].mean()
        
        # ==========================================
        # SECTION A: VITAL SIGNS (KPIs)
        # ==========================================
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PM2.5 Level", f"{kpi_pm25:.0f} µg/m³", "Fine Particles")
        c2.metric("PM10 Level", f"{kpi_pm10:.0f} µg/m³", "Dust / Coarse")
        c3.metric("Wind Speed", f"{kpi_wind:.1f} km/h", "Dispersion Factor")
        c4.metric("Last Updated", str(latest_time))

        st.divider()

        # ==========================================
        # SECTION B: REAL-TIME MONITORING (The "Previous Graphs")
        # ==========================================
        st.subheader("Live Monitoring")
        
        m1, m2 = st.columns(2)
        
        with m1:
            st.markdown("**Severity Leaderboard (Top 10)**")
            # We ALWAYS use 'global_df' here so we can see the "Top 10" 
            # even when looking at a specific city (for comparison context)
            
            # Get latest slice of GLOBAL data
            global_latest = global_df[global_df['timestamp'] == global_df['timestamp'].max()]
            top_10 = global_latest.nlargest(10, 'pm2_5')
            
            fig_bar = px.bar(
                top_10, 
                x='pm2_5', y='district', 
                orientation='h', 
                color='pm2_5', color_continuous_scale='Reds',
                text_auto=True
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig_bar, use_container_width=True)

        with m2:
            st.markdown(f"**24-Hour Trend ({selected_city})**")
            # We use 'filtered_df' here to show the trend for the selection
            
            # If "All Punjab", simplify chart to show only Top 5 cities to avoid clutter
            if selected_city == "All Punjab":
                top_cities = global_latest.nlargest(5, 'pm2_5')['district'].tolist()
                line_data = global_df[global_df['district'].isin(top_cities)]
                title_text = "Trends (Top 5 Polluted Cities)"
            else:
                line_data = filtered_df
                title_text = f"PM2.5 Trend: {selected_city}"

            fig_line = px.line(
                line_data, 
                x='timestamp', y='pm2_5', 
                color='district',
                markers=True
            )
            st.plotly_chart(fig_line, use_container_width=True)

        st.divider()

        # ==========================================
        # SECTION C: SMOG DYNAMICS (The "New Analysis")
        # ==========================================
        st.subheader(f"Smog Diagnostics: {selected_city}")
        
        a1, a2 = st.columns(2)

        with a1:
            st.markdown("**Wind Dispersion Analysis**")
            # Scatter Plot: Does Wind Speed (X) lower PM2.5 (Y)?
            fig_scatter = px.scatter(
                filtered_df, # Use filtered data
                x="wind_speed", y="pm2_5",
                color="pm2_5", color_continuous_scale="RdYlGn_r",
                size="pm10", 
                trendline="ols", # Requires statsmodels
                labels={"wind_speed": "Wind Speed (km/h)", "pm2_5": "PM2.5"}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
            st.caption("**Trendline:** Downward slope = Wind is clearing the smog.")

        with a2:
            st.markdown("**Pollution Source Map (Wind Rose)**")
            # Polar Chart: Where is the wind coming from?
            
            # Group by direction
            rose_data = filtered_df.groupby('wind_cardinal')[['pm2_5']].mean().reset_index()
            
            fig_rose = px.bar_polar(
                rose_data,
                r="pm2_5", theta="wind_cardinal",
                color="pm2_5", color_continuous_scale="Reds",
                template="plotly_dark"
            )
            st.plotly_chart(fig_rose, use_container_width=True)
            st.caption("**Insight:** Bars point to the pollution source direction.")

        # ==========================================
        # RAW DATA EXPANDER
        # ==========================================
        with st.expander("View Raw Data"):
            st.dataframe(filtered_df)

    else:
        st.warning("No data available yet.")

except Exception as e:
    st.error(f"App Error: {e}")