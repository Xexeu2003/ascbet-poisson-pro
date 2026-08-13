import streamlit as st
import requests
import json
from datetime import datetime, date
import pandas as pd
from fpdf import FPDF
import math

API_BASE = 'https://v3.football.api-sports.io'

@st.cache_data(ttl=300)
def get_headers():
    key = st.secrets.get('API_FOOTBALL_KEY', None)
    if not key:
        st.error('API key not found in secrets')
        st.stop()
    return {'x-apisports-key': key}

def handle_api_error(response):
    if response.status_code == 401:
        raise Exception('Invalid API key (401)')
    elif response.status_code == 429:
        raise Exception('Rate limit exceeded (429)')
    elif response.status_code == 404:
        raise Exception('Endpoint not found (404)')
    response.raise_for_status()
    return response.json()

leagues = {
    'Finlândia Veikkausliiga': 244,
    'Islândia Besta deild': 166,
    'Alemanha Bundesliga 3': 80,
    'Eredivisie': 88,
    'Eerste Divisie': 89,
    'Bundesliga 1': 78,
    'Bundesliga 2': 79,
    'Regionalliga': 454,
    'Oberliga': 455,
    'Bélgica Jupiler Pro League': 144,
    'Challenger Pro League': 145,
    'Dinamarca Superliga': 119,
    '1st Division': 120,
    'Polônia Ekstraklasa': 106,
    'I Liga': 107,
    'Hungria NB I': 271,
    'NB II': 272,
    'Austrália A-League Men': 188,
    'Argentina Liga Profesional': 128,
    'Primera Nacional': 129
}

def get_seasons():
    current = datetime.now().year
    return list(range(2023, current + 2)) + [2026]

def fetch_fixtures(league_id, season, date_from, date_to):
    params = {'league': league_id, 'season': season, 'from': date_from, 'to': date_to}
    resp = requests.get(f'{API_BASE}/fixtures', headers=get_headers(), params=params, timeout=10)
    data = handle_api_error(resp)
    return data.get('response', [])

def fetch_team_stats(team_id, season):
    params = {'team': team_id, 'season': season}
    resp = requests.get(f'{API_BASE}/teams/statistics', headers=get_headers(), params=params, timeout=10)
    data = handle_api_error(resp)
    return data.get('response', {})

def fetch_h2h(team1, team2):
    params = {'h2h': f'{team1}-{team2}', 'last': 10}
    resp = requests.get(f'{API_BASE}/fixtures/headtohead', headers=get_headers(), params=params, timeout=10)
    data = handle_api_error(resp)
    return data.get('response', [])

def fetch_last_games(team_id, last=10):
    params = {'team': team_id, 'last': last}
    resp = requests.get(f'{API_BASE}/fixtures', headers=get_headers(), params=params, timeout=10)
    data = handle_api_error(resp)
    return data.get('response', [])

def safe_extract(match, key_path, default=0):
    try:
        val = match
        for k in key_path:
            val = val[k]
        return val if val is not None else default
    except:
        return default

def compute_averages(fixtures, h2h, last_games_home, last_games_away, league_avg):
    # 50% last10, 30% league, 20% h2h with redistribution
    weights = {'last': 0.5, 'league': 0.3, 'h2h': 0.2}
    if not h2h:
        weights['last'] += weights['h2h'] / 2
        weights['league'] += weights['h2h'] / 2
        weights['h2h'] = 0
    # defensive extraction of goals, corners, cards
    # simplified combined avg calculation
    return {'goals_ft': 2.6, 'goals_ht': 1.1, 'corners': 10.5, 'cards': 4.2}  # placeholder logic

def poisson_pmf(k, lamb):
    return (math.exp(-lamb) * lamb ** k) / math.factorial(k)

def calc_probs(avg_goals_ht, avg_goals_ft, avg_corners, avg_cards, corner_line=10.5, card_line=4.5):
    # Poisson calculations
    p_over05ht = 1 - poisson_pmf(0, avg_goals_ht)
    p_over15ft = sum(poisson_pmf(k, avg_goals_ft) for k in range(2, 10))
    p_btts = 0.48  # placeholder
    p_over_corners = 0.52
    p_over_cards = 0.55
    return {
        'Over 0.5 HT': round(p_over05ht * 100, 1),
        'Over 1.5 FT': round(p_over15ft * 100, 1),
        'BTTS': round(p_btts * 100, 1),
        f'Over {corner_line} Corners': round(p_over_corners * 100, 1),
        f'Over {card_line} Cards': round(p_over_cards * 100, 1)
    }

def main():
    st.title('Football Analyzer - Streamlit App')
    st.sidebar.header('Config')
    league_name = st.sidebar.selectbox('Liga', list(leagues.keys()))
    league_id = st.sidebar.number_input('ID Liga (editável)', value=leagues[league_name], step=1)
    season = st.sidebar.selectbox('Temporada', get_seasons())
    date_from = st.sidebar.date_input('De', date(2024, 8, 1))
    date_to = st.sidebar.date_input('Até', date.today())
    if st.sidebar.button('Buscar Fixtures'):
        try:
            fixtures = fetch_fixtures(league_id, season, str(date_from), str(date_to))
            st.session_state['fixtures'] = fixtures
        except Exception as e:
            st.error(str(e))
    fixtures = st.session_state.get('fixtures', [])
    if not fixtures:
        st.info('Nenhuma fixture carregada. Busque acima.')
        return
    selected = st.selectbox('Selecione Fixture', [f"{f['teams']['home']['name']} vs {f['teams']['away']['name']}" for f in fixtures])
    if st.button('Analisar'):
        idx = [f"{f['teams']['home']['name']} vs {f['teams']['away']['name']}" for f in fixtures].index(selected)
        fix = fixtures[idx]
        home_id = fix['teams']['home']['id']
        away_id = fix['teams']['away']['id']
        try:
            last_h = fetch_last_games(home_id)
            last_a = fetch_last_games(away_id)
            h2h = fetch_h2h(home_id, away_id)
            league_avg = {}  # calc from completed fixtures
            avgs = compute_averages(fixtures, h2h, last_h, last_a, league_avg)
            probs = calc_probs(avgs['goals_ht'], avgs['goals_ft'], avgs['corners'], avgs['cards'])
            df = pd.DataFrame([probs])
            st.dataframe(df)
            if st.button('Export CSV'):
                df.to_csv('analysis.csv', index=False)
                st.success('CSV salvo')
            if st.button('Export PDF'):
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font('Arial', size=12)
                pdf.cell(0, 10, 'Football Analysis', ln=True)
                pdf.output('analysis.pdf')
                with open('analysis.pdf', 'rb') as f:
                    st.download_button('Download PDF', f.read(), 'analysis.pdf')
        except Exception as e:
            st.error(str(e))

if __name__ == '__main__':
    main()
