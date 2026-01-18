import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
from datetime import datetime, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="Punjab Smog Intelligence", page_icon="🌫️", layout="wide")

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
# Replaced Sidebar with a clean top-row filter
f1, f2 = st.columns([1, 3]) # f1 is smaller for the dropdown

with f1:
    st.markdown("**Select Time Range:**")
    time_option = st.selectbox(
        "Time Range",
        ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "Last 6 Months", "Last 1 Year", "Custom Range", "Specific Date"],
        label_visibility="collapsed" # Hides the duplicate label for a cleaner look
    )

# --- TIME LOGIC ---
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
    with f2:
        c_col1, c_col2 = st.columns(2)
        c_start = c_col1.date_input("Start Date", value=end_date - timedelta(days=7))
        c_end = c_col2.date_input("End Date", value=end_date)
        start_date = datetime.combine(c_start, datetime.min.time())
        end_date = datetime.combine(c_end, datetime.max.time())
elif time_option == "Specific Date":
    with f2:
        spec_date = st.date_input("Select Date", value=end_date)
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
    if df.empty: return df
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
                text='pm2_5' # Clean label for bar chart is usually fine
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

        with c2:
            st.subheader("Trend Comparison")
            
            # Smart City Selection
            fixed = ['Islamabad', 'Lahore', 'Multan', 'Faisalabad', 'Gujranwala', 'Sargodha']
            top_2 = latest_df.nlargest(2, 'pm2_5')['district'].tolist()
            final_list = list(set(fixed + top_2))
            
            trend_data = df[df['district'].isin(final_list)]
            
            fig_line = px.line(
                trend_data, 
                x='timestamp', y='pm2_5', 
                color='district',
                markers=True,
                # REMOVED: text='pm2_5' (As requested, makes it cleaner)
                title=f"Comparison: Major Cities + {', '.join(top_2)}"
            )
            st.plotly_chart(fig_line, use_container_width=True)

        st.divider()

        # ==========================================
        # PART 2: SMOG DIAGNOSTICS (Deep Dive)
        # ==========================================
        st.header("Smog Diagnostics")
        
        # --- LOCAL FILTER (Placed directly in this section) ---
        d_col1, d_col2 = st.columns([1, 3])
        with d_col1:
            st.markdown("**Select District to Analyze:**")
            districts = sorted(df['district'].unique())
            selected_city = st.selectbox("District", districts, label_visibility="collapsed")

        # Filter Logic
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
                st.plotly_chart(fig_scatter, use_container_width=True)

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
                st.plotly_chart(fig_rose, use_container_width=True)

            with st.expander(f"View Raw Data for {selected_city}"):
                st.dataframe(city_df)
        else:
            st.warning(f"No data for {selected_city}")

    else:
        st.warning("No data found for this time range.")

except Exception as e:
    st.error(f"Error: {e}")