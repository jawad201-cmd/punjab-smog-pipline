import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

# --- HEADER & TITLE ---
st.title("Punjab Smog Intelligence Platform")
st.markdown("Analyze how **Wind Speed** and **Wind Direction** impact Smog levels (PM2.5 & PM10).")
st.divider()

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db_connection():
    db_url = st.secrets["connections"]["db_url"]
    return create_engine(db_url)

# --- LOAD DATA ---
def load_data():
    engine = get_db_connection()
    # Fetch more data (2000 rows) to ensure good charts
    query = """
    SELECT * FROM smog_metrics 
    ORDER BY timestamp DESC 
    LIMIT 2000;
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

# --- HELPER: PROCESS WIND DIRECTION ---
def add_wind_cardinals(df):
    """Converts 0-360 degrees into N, NE, E, SE... for the chart"""
    bins = [0, 45, 90, 135, 180, 225, 270, 315, 360]
    labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    # Use 'include_lowest' to catch 0 degrees
    df['wind_cardinal'] = pd.cut(df['wind_dir'], bins=bins, labels=labels, include_lowest=True)
    return df

# --- MAIN DASHBOARD LOGIC ---
try:
    with st.spinner("Fetching pollution data..."):
        raw_df = load_data()
        df = add_wind_cardinals(raw_df)

    # ==========================================
    # 1. SIDEBAR FILTER (The City Chooser)
    # ==========================================
    with st.sidebar:
        st.header("Filter Controls")
        
        # Get unique list of districts sorted alphabetically
        districts = sorted(df['district'].unique())
        # Add an "All Punjab" option at the top
        districts.insert(0, "All Punjab")
        
        selected_city = st.selectbox("Choose a District:", districts)
        
        st.info(f"Viewing analysis for: **{selected_city}**")
        st.markdown("---")
        st.caption("Data updates hourly via GitHub Actions.")

    # FILTER THE DATAFRAME BASED ON SELECTION
    if selected_city != "All Punjab":
        filtered_df = df[df['district'] == selected_city]
    else:
        filtered_df = df

    # Only show dashboard if we have data for that city
    if not filtered_df.empty:
        
        # ==========================================
        # 2. KPI ROW (Live Status)
        # ==========================================
        # Get the single most recent record for the metrics
        latest_record = filtered_df.iloc[0] 
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current PM2.5", f"{latest_record['pm2_5']:.0f}", "Fine Particles")
        col2.metric("Current PM10", f"{latest_record['pm10']:.0f}", "Dust / Coarse")
        col3.metric("Wind Speed", f"{latest_record['wind_speed']:.1f} km/h", "Dispersion Power")
        col4.metric("Wind Direction", f"{latest_record['wind_cardinal']}", f"{latest_record['wind_dir']}°")

        st.divider()

        # ==========================================
        # 3. ANALYSIS CHARTS (The "Why")
        # ==========================================
        
        c1, c2 = st.columns(2)

        # CHART A: WIND SPEED IMPACT (Scatter Plot)
        with c1:
            st.subheader("Does Wind clear the Smog?")
            st.caption(f"Visualizing the relationship between Wind Speed and PM2.5 in **{selected_city}**.")
            
            fig_scatter = px.scatter(
                filtered_df,
                x="wind_speed",
                y="pm2_5",
                color="pm2_5",
                color_continuous_scale="RdYlGn_r", # Green=Low, Red=High
                size="pm10", # Bubbles get bigger if there is also dust
                trendline="ols", # Shows the trend line (Requires statsmodels)
                title="Impact of Wind Speed on PM2.5",
                labels={"wind_speed": "Wind Speed (km/h)", "pm2_5": "PM2.5 Level"}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
            st.info("**Insight:** If the trend line goes **DOWN** , it proves that higher wind speeds are successfully blowing the smog away.")

        # CHART B: POLLUTION SOURCE (Wind Rose)
        with c2:
            st.subheader("Where is the Smog coming from?")
            st.caption("Average PM2.5 and PM10 levels based on Wind Direction.")
            
            # Group data by direction (N, NE, E...) and take the average pollution
            rose_data = filtered_df.groupby('wind_cardinal')[['pm2_5', 'pm10']].mean().reset_index()
            
            # We melt the data so we can show both PM2.5 and PM10 on the same chart
            rose_melted = rose_data.melt(id_vars='wind_cardinal', var_name='Pollutant', value_name='Concentration')

            fig_rose = px.bar_polar(
                rose_melted,
                r="Concentration",
                theta="wind_cardinal",
                color="Pollutant",
                template="plotly_dark",
                color_discrete_map={"pm2_5": "#FF4B4B", "pm10": "#FFA500"}, # Red for PM2.5, Orange for PM10
                title=f"Pollution Source Map ({selected_city})"
            )
            st.plotly_chart(fig_rose, use_container_width=True)
            st.info("💡 **Insight:** The longest bars point to the **Source**. (e.g., If 'E' is huge, pollution comes from the East).")

        # ==========================================
        # 4. RAW DATA
        # ==========================================
        with st.expander(f"View Raw Data for {selected_city}"):
            st.dataframe(filtered_df)

    else:
        st.warning(f"No data found for {selected_city}. Wait for the next scheduled run.")

except Exception as e:
    st.error(f"App Error: {e}")
    st.caption("Make sure 'statsmodels' is in your requirements.txt for the trendline feature.")