import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

st.title("Punjab Smog Intelligence Platform")
st.markdown("Real-time monitoring of PM2.5, PM10, Wind, and Fire data across 42 districts.")
st.divider()

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db_connection():
    db_url = st.secrets["connections"]["db_url"]
    return create_engine(db_url)

# --- LOAD DATA ---
def load_data():
    engine = get_db_connection()
    # Fetch all columns to ensure we have PM10 and Wind
    query = """
    SELECT * FROM smog_metrics 
    ORDER BY timestamp DESC 
    LIMIT 1000;
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

# --- MAIN DASHBOARD ---
try:
    with st.spinner("Fetching live telemetry..."):
        df = load_data()

    if not df.empty:
        # Get the latest snapshot (most recent timestamp)
        latest_time = df['timestamp'].max()
        current_data = df[df['timestamp'] == latest_time]

        # ==========================================
        # 1. KPI ROW: VITAL SIGNS
        # ==========================================
        # We now calculate averages for ALL key factors, not just PM2.5
        avg_pm25 = current_data['pm2_5'].mean()
        avg_pm10 = current_data['pm10'].mean()
        avg_wind = current_data['wind_speed'].mean()
        total_fire = current_data['provincial_fire_load'].iloc[0]

        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("Avg PM2.5 (Fine Particles)", f"{avg_pm25:.0f} µg/m³", help="Combustion, smoke, exhaust")
        col2.metric("Avg PM10 (Dust/Coarse)", f"{avg_pm10:.0f} µg/m³", help="Road dust, construction, storms")
        # Inverse delta color for wind: Green if high (good), Red if low (bad)
        col3.metric("Avg Wind Speed", f"{avg_wind:.1f} km/h", delta_color="normal", help="Higher wind clears smog")
        col4.metric("Fire Intensity (FRP)", f"{total_fire:.0f} MW", "NASA Data")

        st.divider()

        # ==========================================
        # 2. ROW 2: CURRENT STATUS
        # ==========================================
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("Critical Districts (PM2.5)")
            # Bar Chart: Worst 10 Cities
            top_10 = current_data.nlargest(10, 'pm2_5')
            fig_bar = px.bar(
                top_10, 
                x='pm2_5', y='district', 
                orientation='h', 
                color='pm2_5', 
                color_continuous_scale='Reds',
                title="Highest PM2.5 Levels Right Now"
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

        with c2:
            st.subheader("24-Hour Trends")
            # Line Chart: Key Cities Over Time
            key_cities = ['Lahore', 'Islamabad', 'Multan', 'Faisalabad']
            trend_df = df[df['district'].isin(key_cities)]
            fig_line = px.line(
                trend_df, 
                x='timestamp', y='pm2_5', 
                color='district',
                title="PM2.5 Fluctuations over Time"
            )
            st.plotly_chart(fig_line, use_container_width=True)

        st.divider()

        # ==========================================
        # 3. ROW 3: SMOG DYNAMICS (THE "WHY")
        # ==========================================
        st.subheader("Smog Diagnostics (Wind & PM10 Analysis)")
        
        d1, d2 = st.columns(2)

        with d1:
            # SCATTER PLOT: Does Wind Speed affect PM2.5?
            # This visually answers: "Is the smog trapped because wind is low?"
            st.markdown("**Impact of Wind on Pollution**")
            fig_scatter = px.scatter(
                df, 
                x='wind_speed', 
                y='pm2_5', 
                color='district',
                trendline="ols", # Adds the trend line (Needs statsmodels)
                title="Correlation: Wind Speed vs PM2.5"
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        with d2:
            # HEATMAP: Correlation Matrix
            # This visually answers: "Is PM2.5 rising with Fire Load or Dust?"
            st.markdown("**Statistical Correlations**")
            # Select only numeric columns relevant to the user
            corr_cols = ['pm2_5', 'pm10', 'wind_speed', 'provincial_fire_load', 'local_fire_count']
            corr_matrix = df[corr_cols].corr()
            
            fig_corr = px.imshow(
                corr_matrix, 
                text_auto=True, 
                color_continuous_scale='RdBu_r', # Red=Positive, Blue=Negative
                title="What drives what? (Correlation Matrix)"
            )
            st.plotly_chart(fig_corr, use_container_width=True)

        # ==========================================
        # 4. RAW DATA EXPLORER
        # ==========================================
        with st.expander("View Raw Data Table"):
            st.dataframe(df)

except Exception as e:
    st.error(f"Dashboard Error: {e}")
    st.info("Ensure requirements.txt includes: streamlit, pandas, sqlalchemy, psycopg2-binary, plotly, statsmodels")