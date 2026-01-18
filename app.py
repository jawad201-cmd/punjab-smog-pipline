import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

# --- HEADER ---
st.title("🌫️ Punjab Smog Intelligence Platform")
st.markdown("Real-time pollution monitoring & historic analysis.")
st.divider()

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db_connection():
    db_url = st.secrets["connections"]["db_url"]
    return create_engine(db_url)

# --- SIDEBAR: GLOBAL TIME FILTER ---
with st.sidebar:
    st.header("Time Filter")
    time_option = st.selectbox(
        "Select Time Range:",
        ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "Last 6 Months", "Last 1 Year", "Custom Range", "Specific Date"]
    )

    # Calculate Start/End Dates based on selection
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=24) # Default

    if time_option == "Last 7 Days":
        start_date = end_date - timedelta(days=7)
    elif time_option == "Last 30 Days":
        start_date = end_date - timedelta(days=30)
    elif time_option == "Last 6 Months":
        start_date = end_date - timedelta(days=180)
    elif time_option == "Last 1 Year":
        start_date = end_date - timedelta(days=365)
    elif time_option == "Custom Range":
        c_start = st.date_input("Start Date", value=end_date - timedelta(days=7))
        c_end = st.date_input("End Date", value=end_date)
        start_date = datetime.combine(c_start, datetime.min.time())
        end_date = datetime.combine(c_end, datetime.max.time())
    elif time_option == "Specific Date":
        spec_date = st.date_input("Select Date", value=end_date)
        start_date = datetime.combine(spec_date, datetime.min.time())
        end_date = datetime.combine(spec_date, datetime.max.time())

# --- LOAD DATA (Dynamic Query) ---
def load_data(start, end):
    engine = get_db_connection()
    # Use parameterized query for security
    query = text("""
        SELECT * FROM smog_metrics 
        WHERE timestamp BETWEEN :start AND :end
        ORDER BY timestamp DESC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"start": start, "end": end})
    return df

# --- HELPER: WIND CARDINALS ---
def add_wind_cardinals(df):
    if df.empty: return df
    bins = [0, 45, 90, 135, 180, 225, 270, 315, 360]
    labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    df['wind_cardinal'] = pd.cut(df['wind_dir'], bins=bins, labels=labels, include_lowest=True)
    return df

# --- MAIN DASHBOARD ---
try:
    # Load Data based on Time Filter
    with st.spinner(f"Loading data for {time_option}..."):
        df = load_data(start_date, end_date)
        df = add_wind_cardinals(df)

    if not df.empty:
        # Get Latest Snapshot for KPIs (First row usually, or max timestamp)
        latest_ts = df['timestamp'].max()
        latest_df = df[df['timestamp'] == latest_ts]

        # ==========================================
        # PART 1: GLOBAL MONITORING (No City Filter)
        # ==========================================
        
        # --- A. TOP STATS ROW ---
        # 1. Most Polluted District
        worst_row = latest_df.loc[latest_df['pm2_5'].idxmax()]
        worst_district = worst_row['district']
        worst_pm25 = worst_row['pm2_5']

        # 2. Averages
        avg_pm25 = latest_df['pm2_5'].mean()
        avg_pm10 = latest_df['pm10'].mean()
        avg_fire = latest_df['provincial_fire_load'].iloc[0] # Same for all rows in a timestamp

        # Display Metrics
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Most Polluted", f"{worst_district}", f"{worst_pm25:.0f} PM2.5", delta_color="inverse")
        m2.metric("Avg PM2.5 (Punjab)", f"{avg_pm25:.0f} µg/m³")
        m3.metric("Avg PM10 (Dust)", f"{avg_pm10:.0f} µg/m³")
        m4.metric("Avg Fire Intensity", f"{avg_fire:.0f} MW")
        m5.metric("Last Updated", str(latest_ts))

        st.divider()

        # --- B. CHARTS ROW ---
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Top 10 Polluted Districts")
            # Top 10 Bar Chart
            top_10 = latest_df.nlargest(10, 'pm2_5')
            
            fig_bar = px.bar(
                top_10, 
                x='pm2_5', y='district', 
                orientation='h', 
                color='pm2_5', color_continuous_scale='Reds',
                text='pm2_5' # PERMANENT LABEL
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

        with c2:
            st.subheader("Trend Comparison")
            
            # --- SMART LINE GRAPH LOGIC ---
            # 1. The Fixed 6 Popular Cities
            fixed_cities = ['Islamabad', 'Lahore', 'Multan', 'Faisalabad', 'Gujranwala', 'Sargodha']
            
            # 2. The Top 2 Polluted Cities (Right Now)
            top_2_polluted = latest_df.nlargest(2, 'pm2_5')['district'].tolist()
            
            # 3. Combine & Remove Duplicates (Set logic)
            final_cities_list = list(set(fixed_cities + top_2_polluted))
            
            # 4. Filter Data
            trend_data = df[df['district'].isin(final_cities_list)]
            
            # 5. Plot
            fig_line = px.line(
                trend_data, 
                x='timestamp', y='pm2_5', 
                color='district',
                markers=True,
                text='pm2_5', # PERMANENT LABEL
                title=f"Comparison: Major Cities + Top Polluted ({', '.join(top_2_polluted)})"
            )
            # Improve label readability so they don't overlap too much
            fig_line.update_traces(textposition="top center")
            st.plotly_chart(fig_line, use_container_width=True)

        st.divider()

        # ==========================================
        # PART 2: SMOG DIAGNOSTICS (With City Filter)
        # ==========================================
        st.header("Smog Diagnostics (Deep Dive)")

        # --- SIDEBAR CITY FILTER (Only affects this section) ---
        with st.sidebar:
            st.divider()
            st.header("City Filter (Diagnostics)")
            districts = sorted(df['district'].unique())
            selected_city = st.selectbox("Select District to Analyze:", districts)
            st.info(f"Showing diagnostics for: **{selected_city}**")

        # Filter Data for Part 2
        city_df = df[df['district'] == selected_city]

        if not city_df.empty:
            d1, d2 = st.columns(2)

            with d1:
                st.markdown(f"**Wind vs Smog Analysis ({selected_city})**")
                fig_scatter = px.scatter(
                    city_df,
                    x="wind_speed", y="pm2_5",
                    color="pm2_5", color_continuous_scale="RdYlGn_r",
                    size="pm10", 
                    trendline="ols", 
                    title=f"Impact of Wind Speed on PM2.5 in {selected_city}"
                )
                st.plotly_chart(fig_scatter, use_container_width=True)

            with d2:
                st.markdown(f"**Pollution Source ({selected_city})**")
                
                # Wind Rose Logic
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
                st.plotly_chart(fig_rose, use_container_width=True)

            with st.expander(f"View Raw Data for {selected_city}"):
                st.dataframe(city_df)
        else:
            st.warning(f"No data found for {selected_city} in the selected time range.")

    else:
        st.warning("No data found for the selected time range. Try selecting 'Last 30 Days'.")

except Exception as e:
    st.error(f"System Error: {e}")