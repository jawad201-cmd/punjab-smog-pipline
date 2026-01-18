import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

st.title("Punjab Smog Intelligence Platform")
st.markdown("Real-time air quality monitoring & predictive analytics for 42 districts.")
st.divider()

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db_connection():
    db_url = st.secrets["connections"]["db_url"]
    return create_engine(db_url)

# --- LOAD DATA ---
def load_data():
    engine = get_db_connection()
    query = """
    SELECT * FROM smog_metrics 
    ORDER BY timestamp DESC 
    LIMIT 1000;
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

# --- HELPER: WIND ROSE DATA ---
def process_wind_rose_data(df):
    # Bin wind direction into 8 cardinal directions (N, NE, E, SE, etc.)
    bins = [0, 45, 90, 135, 180, 225, 270, 315, 360]
    labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    df['wind_cardinal'] = pd.cut(df['wind_dir'], bins=bins, labels=labels, include_lowest=True)
    
    # Group by direction and calculate average PM2.5
    wind_rose = df.groupby('wind_cardinal')[['pm2_5', 'wind_speed']].mean().reset_index()
    return wind_rose

# --- MAIN APP LOGIC ---
try:
    with st.spinner("Crunching numbers..."):
        df = load_data()

    # Create Tabs
    tab1, tab2 = st.tabs(["Live Monitoring", "Deep Dive Analysis"])

    # ==========================================
    # TAB 1: LIVE MONITORING (Your Original Dashboard)
    # ==========================================
    with tab1:
        if not df.empty:
            latest_time = df['timestamp'].max()
            current_data = df[df['timestamp'] == latest_time]
            
            # KPI Metrics
            avg_pm25 = current_data['pm2_5'].mean()
            worst_city = current_data.loc[current_data['pm2_5'].idxmax(), 'district']
            fire_load = current_data['provincial_fire_load'].iloc[0]

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Avg PM2.5 (Punjab)", f"{avg_pm25:.0f} µg/m³")
            col2.metric("Worst City", f"{worst_city}", f"{current_data['pm2_5'].max():.0f}")
            col3.metric("Fire Intensity", f"{fire_load:.0f} MW")
            col4.metric("Last Updated", str(latest_time))

            st.divider()

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Top 10 Polluted Districts")
                top_10 = current_data.nlargest(10, 'pm2_5')
                fig_bar = px.bar(top_10, x='pm2_5', y='district', orientation='h', color='pm2_5', color_continuous_scale='Reds')
                fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_bar, use_container_width=True)
            
            with c2:
                st.subheader("Smog Trends (Key Cities)")
                key_cities = ['Lahore', 'Islamabad', 'Multan', 'Faisalabad']
                trend_df = df[df['district'].isin(key_cities)]
                fig_line = px.line(trend_df, x='timestamp', y='pm2_5', color='district')
                st.plotly_chart(fig_line, use_container_width=True)

    # ==========================================
    # TAB 2: DEEP DIVE ANALYSIS (New!)
    # ==========================================
    with tab2:
        st.subheader("What drives the Smog?")
        
        # 1. Correlation Matrix (Heatmap)
        st.markdown("### 1. The Correlation Matrix")
        st.markdown("This heatmap proves relationships. **Red (1.0)** means they move together. **Blue (-1.0)** means opposite.")
        
        # Select numeric columns only for correlation
        corr_cols = ['pm2_5', 'pm10', 'wind_speed', 'provincial_fire_load', 'local_fire_count']
        corr_matrix = df[corr_cols].corr()
        
        fig_corr = px.imshow(
            corr_matrix, 
            text_auto=True, 
            color_continuous_scale='RdBu_r', # Red=Positive, Blue=Negative
            title="Correlation Heatmap (PM2.5 vs Wind vs Fire)"
        )
        st.plotly_chart(fig_corr, use_container_width=True)

        col_a, col_b = st.columns(2)
        
        # 2. Scatter Plot (Wind vs Smog)
        with col_a:
            st.markdown("### 2. Does Wind clear the Smog?")
            fig_scatter = px.scatter(
                df, 
                x='wind_speed', 
                y='pm2_5', 
                color='district',
                trendline="ols", # Needs statsmodels
                title="Wind Speed vs PM2.5 Impact"
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        # 3. Wind Rose (Pollution Source)
        with col_b:
            st.markdown("### 3. Pollution Source (Wind Rose)")
            # Process data for Wind Rose
            wind_rose_data = process_wind_rose_data(df)
            
            fig_rose = px.bar_polar(
                wind_rose_data, 
                r="pm2_5", 
                theta="wind_cardinal", 
                color="pm2_5", 
                color_continuous_scale="Reds",
                title="Avg PM2.5 by Wind Direction"
            )
            st.plotly_chart(fig_rose, use_container_width=True)

except Exception as e:
    st.error(f"Dashboard Error: {e}")