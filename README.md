# Punjab Smog Intelligence Platform

A real-time air quality monitoring and analysis dashboard for Punjab, Pakistan. This platform provides actionable insights on pollution patterns across 40+ districts, designed for environmental agencies, public health officials, researchers, and the general public.

**Live Demo:** https://punjab-smog-dashboard.vercel.app/

## Overview

Punjab faces severe seasonal smog affecting millions of residents annually. This platform addresses the challenge by centralizing fragmented air quality data into a unified, interactive dashboard that enables data-driven decision making for environmental policy and public health advisories.

## Features

- **Real-Time Monitoring** — Live PM2.5 and PM10 tracking across 40+ districts with automatic data refresh
- **Interactive Visualizations** — 10+ charts including trend comparisons, pollution rankings, and correlation analysis
- **Fire-Pollution Correlation** — Lag-based analysis (0-2 days) showing how agricultural fires impact air quality
- **Wind Pattern Analysis** — Wind rose diagrams and directional mapping to understand pollution transport
- **District Diagnostics** — Deep-dive analysis for individual districts with neighboring area comparisons
- **Report Generation** — One-click PDF and PowerPoint export for stakeholder presentations
- **Mobile Responsive** — Full functionality on desktop, tablet, and mobile devices

## How It Works
```
Data Sources → Pipeline → Database → Frontend → User
```

### 1. Data Collection
- **Air Quality Data:** PM2.5 and PM10 concentrations from monitoring stations
- **Fire Data:** NASA FIRMS (Fire Information for Resource Management System)
- **Weather Data:** Wind speed, wind direction from meteorological APIs

### 2. Data Pipeline
- GitHub Actions runs scheduled jobs to collect and process data
- Python scripts handle ETL (Extract, Transform, Load) operations
- Processed data is pushed to the database

### 3. Database
- Supabase (PostgreSQL) stores all historical and real-time data
- Real-time subscriptions enable instant updates to connected clients
- Row Level Security (RLS) ensures data protection

### 4. Frontend
- Vanilla JavaScript with ES6 modules for clean, maintainable code
- Plotly.js powers all interactive charts and maps
- Responsive CSS ensures usability across all devices

### 5. Deployment
- GitHub Actions handles CI/CD pipeline
- Vercel provides edge deployment with global CDN
- Automatic deployments on every push to main branch

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | HTML, CSS, JavaScript (ES6) |
| Visualization | Plotly.js |
| Database | Supabase (PostgreSQL) |
| Real-time | Supabase Realtime Subscriptions |
| CI/CD | GitHub Actions |
| Hosting | Vercel (Edge Network) |
| Reports | jsPDF, PptxGenJS, html2canvas |

## Dashboard Sections

### Key Metrics
- Most Polluted District
- Average PM2.5 / PM10 levels
- Fire Intensity (FRP)
- Total Fire Activity
- Last Updated Timestamp

### Visualizations
| Chart | Description |
|-------|-------------|
| Trend Comparison | Time-series PM2.5 comparison across major cities |
| Top 10 Polluted | Horizontal bar chart of highest pollution districts |
| Global Fire Lag | Province-wide fire-pollution correlation |
| Wind Rose Map | Geographic visualization of pollution transport |
| Wind Impact | Scatter plot of wind speed vs PM2.5 |
| District Fire Lag | Local fire correlation with 5 nearest neighbors |

### District Diagnostics
- Wind rose chart showing directional pollution sources
- Downwind impact map with nearby district labels
- PM2.5/PM10 ratio analysis
- Wind direction band analysis

## Project Structure
```
punjab-smog-dashboard/
├── index.html              # Main HTML file
├── css/
│   └── styles.css          # All styling
├── js/
│   ├── app.js              # Main application logic
│   ├── config.js           # Configuration constants
│   ├── data.js             # Data fetching & processing
│   ├── charts.js           # Chart rendering functions
│   ├── analysis.js         # Data analysis & interpretations
│   ├── locations.js        # District coordinates
│   └── report.js           # PDF/PPTX generation
├── .github/workflows/
│   └── deploy.yml          # CI/CD workflow
├── build.js                # Build script
└── vercel.json             # Vercel configuration
```

## Getting Started

### Prerequisites
- Node.js 18+
- Supabase account
- Vercel account (for deployment)

### Local Development

1. Clone the repository
```bash
   git clone https://github.com/yourusername/punjab-smog-dashboard.git
   cd punjab-smog-dashboard
```

2. Update `js/config.js` with your Supabase credentials
```javascript
   export const SUPABASE_URL = 'your-supabase-url';
   export const SUPABASE_ANON_KEY = 'your-anon-key';
```

3. Serve locally
```bash
   npx serve .
```

4. Open `http://localhost:3000` in your browser

### Deployment

1. Push to GitHub
2. Connect repository to Vercel
3. Add environment secrets in GitHub:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `VERCEL_TOKEN`
   - `VERCEL_ORG_ID`
   - `VERCEL_PROJECT_ID`
4. GitHub Actions will automatically build and deploy

## Use Cases

- **Environmental Compliance** — Monitor pollution levels against regulatory standards
- **Public Health Advisories** — Issue timely warnings based on air quality data
- **Agricultural Impact Assessment** — Track how crop burning affects regional air quality
- **Policy Development** — Data-driven insights for environmental regulations
- **Research & Analysis** — Historical data access for academic studies

## License

MIT License — feel free to use and modify for your own projects.

## Contact

For questions, collaboration, or similar project inquiries:

- **LinkedIn:** www.linkedin.com/in/jawad-ahmad-05b33036b
- **Email:** jawadprod1999@gmail.com
