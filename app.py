import streamlit as st
import requests
import pandas as pd
import math
from datetime import datetime, timedelta
from fpdf import FPDF
import os

st.set_page_config(page_title="Football Match Analyzer", layout="wide")

API_KEY = st.secrets.get("API_FOOTBALL_KEY", os.getenv("API_FOOTBALL_KEY"))
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

@st.cache_data(ttl=3600)
def api_get(endpoint, params=None):
    if not API_KEY:
        st.error("API key not configured. Set API_FOOTBALL_KEY in secrets.")
        st.stop()
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None

def poisson_pmf(k, lamb):
    if lamb <= 0:
        return 0.0
    return (math.exp(-lamb) * lamb ** k) / math.factorial(k)

def calc_probs(home_avg, away_avg):
    p = {}
    # Over 0.5 HT (simplified using 0.55*FT avg)
    ht_home = home_avg * 0.55
    ht_away = away_avg * 0.55
    p["over_0.5_ht"] = 1 - sum(poisson_pmf(i, ht_home) * poisson_pmf(j, ht_away) for i in range(1) for j in range(1))
    # Over 1.5 FT
    p["over_1.5_ft"] = 1 - sum(poisson_pmf(i, home_avg) * poisson_pmf(j, away_avg) for i in range(2) for j in range(2))
    # BTTS
    p["btts"] = sum(poisson_pmf(i, home_avg) * poisson_pmf(j, away_avg) for i in range(1, 6) for j in range(1, 6))
    return p

leagues = {39: "Premier League", 140: "La Liga", 78: "Bundesliga", 135: "Serie A", 61: "Ligue 1"}
current_year = datetime.now().year
seasons = list(range(2020, current_year + 2))

st.title("Football Match Analyzer (API-Football v3 + Poisson)")

col1, col2, col3 = st.columns(3)
with col1:
    league_id = st.selectbox("League", list(leagues.keys()), format_func=lambda x: leagues[x])
with col2:
    season = st.selectbox("Season", seasons, index=len(seasons)-2)
with col3:
    date_range = st.date_input("Date range", [datetime.now() - timedelta(days=30), datetime.now()])

if st.button("Load Fixtures"):
    fixtures = api_get("fixtures", {"league": league_id, "season": season, "from": str(date_range[0]), "to": str(date_range[1])})
    if fixtures and fixtures.get("response"):
        df = pd.DataFrame([{"id": f["fixture"]["id"], "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"], "date": f["fixture"]["date"]} for f in fixtures["response"]])
        st.dataframe(df)
        selected = st.selectbox("Select fixture ID", df["id"].tolist())
        if selected:
            h2h = api_get("fixtures/headtohead", {"h2h": f"{df[df.id==selected].home.iloc[0]}-{df[df.id==selected].away.iloc[0]}", "season": season})
            last10 = api_get("fixtures", {"team": df[df.id==selected].home.iloc[0], "last": 10})
            stats = api_get("teams/statistics", {"league": league_id, "season": season, "team": df[df.id==selected].home.iloc[0]})
            st.subheader("Last 10 & H2H")
            st.json({"h2h": h2h, "last10": last10, "stats": stats})
            home_avg = 1.5  # placeholder from stats
            away_avg = 1.2
            probs = calc_probs(home_avg, away_avg)
            st.write("Poisson Probabilities:", probs)
            line = st.slider("Corners line", 8, 14, 10)
            st.write(f"Corners > {line} probability placeholder")
            if st.button("Export CSV"):
                df.to_csv("matches.csv", index=False)
                st.success("CSV saved")
            if st.button("Export PDF"):
                pdf = FPDF()
                pdf.add_page()
                pdf.cell(0,10,"Match Analysis")
                pdf.output("report.pdf")
                st.success("PDF saved")
    else:
        st.warning("No fixtures found.")

st.caption("Secure key loading • Cached requests • Error handling enabled")
