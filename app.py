import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Tracker", page_icon="🌫️", layout="wide")

# --- HEADER ---
st.title("Punjab Smog Intelligence Platform")
st.markdown("Real-time air quality monitoring across 42 districts in Punjab.")
st.divider()

# --- DATABASE CONNECTION ---
# We use cache_resource to keep the connection open for speed
@st.cache_resource
def get_db_connection():
    # Reads the secrets.toml file automatically
    db_url = st.secrets["connections"]["db_url"]
    return create_engine(db_url)

# --- LOAD DATA ---
def load_data():
    engine = get_db_connection()
    # Fetch the latest 500 records, sorted by newest first
    query = """
    SELECT timestamp, district, pm2_5, wind_speed, provincial_fire_load 
    FROM smog_metrics 
    ORDER BY timestamp DESC 
    LIMIT 600;
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

# --- MAIN DASHBOARD ---
try:
    with st.spinner("Connecting to Supabase Cloud..."):
        df = load_data()

    # 1. KPI SECTION (The "Big Numbers")
    if not df.empty:
        latest_time = df['timestamp'].max()
        current_data = df[df['timestamp'] == latest_time]
        
        # Calculate Metrics
        avg_pm25 = current_data['pm2_5'].mean()
        max_pm25 = current_data['pm2_5'].max()
        worst_city = current_data.loc[current_data['pm2_5'].idxmax(), 'district']
        fire_load = current_data['provincial_fire_load'].iloc[0]

        # Display Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Avg PM2.5 (Punjab)", f"{avg_pm25:.0f} µg/m³")
        col2.metric("Worst City", f"{worst_city}", f"{max_pm25:.0f} µg/m³", delta_color="inverse")
        col3.metric("Fire Intensity (FRP)", f"{fire_load:.0f} MW")
        col4.metric("Last Updated", str(latest_time))
    
    st.divider()

    # 2. VISUALIZATION SECTION
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Most Polluted Districts")
        # Top 10 Worst Cities Chart
        top_10 = current_data.nlargest(10, 'pm2_5')
        fig_bar = px.bar(
            top_10, 
            x='pm2_5', y='district', 
            orientation='h', 
            color='pm2_5', color_continuous_scale='Reds',
            title="Current PM2.5 Levels (Highest to Lowest)"
        )
        fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_right:
        st.subheader("Smog Trends (24h)")
        # Line Chart for Key Cities
        key_cities = ['Lahore', 'Islamabad', 'Multan', 'Faisalabad']
        trend_df = df[df['district'].isin(key_cities)]
        
        fig_line = px.line(
            trend_df, 
            x='timestamp', y='pm2_5', color='district',
            title="PM2.5 History (Key Cities)"
        )
        st.plotly_chart(fig_line, use_container_width=True)

    # 3. DATA TABLE
    with st.expander("View Raw Data Table"):
        st.dataframe(df)

except Exception as e:
    st.error(f"Could not load data. Error: {e}")
    st.info("Check if your .streamlit/secrets.toml file is set up correctly.")