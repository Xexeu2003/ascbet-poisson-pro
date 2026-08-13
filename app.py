import streamlit as st
import requests
import math
import pandas as pd
from fpdf import FPDF
import io

BASE_URL = 'https://v3.football.api-sports.io'

# Função para obter cabeçalhos da API com chave segura
def get_headers():
    try:
        key = st.secrets['API_FOOTBALL_KEY']
        return {'x-apisports-key': key}
    except:
        st.error('Chave API_FOOTBALL_KEY não encontrada em secrets.')
        return None

# Função pequena para chamadas com timeout e tratamento de erros
def api_call(endpoint, params):
    headers = get_headers()
    if not headers:
        return None
    try:
        resp = requests.get(f'{BASE_URL}{endpoint}', headers=headers, params=params, timeout=10)
        if resp.status_code == 401:
            st.error('Erro 401: Chave inválida.')
            return None
        if resp.status_code == 403:
            st.error('Erro 403: Acesso negado.')
            return None
        if resp.status_code == 429:
            st.error('Erro 429: Limite de requisições excedido.')
            return None
        if resp.status_code != 200:
            st.error(f'Erro API: {resp.status_code}')
            return None
        return resp.json()
    except Exception as e:
        st.error(f'Erro de conexão: {str(e)}')
        return None

# Função para Poisson PMF
def poisson_pmf(k, lam):
    if lam <= 0:
        return 0.0
    return (lam ** k * math.exp(-lam)) / math.factorial(k)

# Função para calcular médias reais dos últimos 10 jogos
@st.cache_data(ttl=3600)
def get_team_averages(team_id, season):
    data = api_call('/fixtures', {'team': team_id, 'last': 10, 'status': 'FT', 'season': season})
    if not data or not data.get('response'):
        return None
    goals_for = []
    goals_against = []
    for f in data['response']:
        if f['teams']['home']['id'] == team_id:
            goals_for.append(f['goals']['home'] or 0)
            goals_against.append(f['goals']['away'] or 0)
        else:
            goals_for.append(f['goals']['away'] or 0)
            goals_against.append(f['goals']['home'] or 0)
    if not goals_for:
        return None
    return {'avg_goals_for': sum(goals_for)/len(goals_for), 'avg_goals_against': sum(goals_against)/len(goals_against)}

# Função para obter fixture por ID
@st.cache_data(ttl=3600)
def get_fixture(fixture_id):
    data = api_call('/fixtures', {'id': fixture_id})
    return data['response'][0] if data and data.get('response') else None

# Função para H2H com IDs
@st.cache_data(ttl=3600)
def get_h2h(home_id, away_id):
    h2h_str = f'{home_id}-{away_id}'
    data = api_call('/fixtures/headtohead', {'h2h': h2h_str, 'last': 10})
    return data['response'] if data else []

# Função para stats da temporada (fallback)
@st.cache_data(ttl=3600)
def get_team_stats(team_id, league_id, season):
    data = api_call('/teams/statistics', {'team': team_id, 'league': league_id, 'season': season})
    if data and data.get('response'):
        return data['response']
    return None

# Ligas permitidas
ligas = {
    'Finlândia Veikkausliiga': 244,
    'Islândia Besta deild': 166,
    'Alemanha 3. Liga': 80,
    'Eredivisie': 88,
    'Eerste Divisie': 89,
    '1. Bundesliga': 78,
    '2. Bundesliga': 79,
    'Bélgica Jupiler Pro League': 144,
    'Challenger Pro League': 145,
    'Dinamarca Superligaen': 119,
    '1. Division': 120,
    'Polônia Ekstraklasa': 106,
    'I Liga': 107,
    'Hungria NB I': 271,
    'NB II': 272,
    'Austrália A-League Men': 188,
    'Argentina Liga Profesional': 128,
    'Primera Nacional': 129
}

st.title('Football Analyzer - Poisson')
st.warning('Cálculo é estimativo e não é garantia de aposta. Use por sua conta e risco.')

# Seletor de liga
liga_nome = st.selectbox('Selecione uma liga', list(ligas.keys()))
league_id = ligas[liga_nome]

# Campo opcional para ID customizado (Regionalliga/Oberliga)
st.info('IDs de Regionalliga e Oberliga devem ser confirmados via /leagues. Use campo abaixo se necessário.')
custom_id = st.text_input('ID de liga personalizado (opcional)', '')
if custom_id.strip().isdigit():
    league_id = int(custom_id.strip())

season = st.selectbox('Temporada', [2023, 2024, 2025, 2026])
from_date = st.date_input('Data inicial')
to_date = st.date_input('Data final')

if st.button('Buscar fixtures'):
    fixtures_data = api_call('/fixtures', {'league': league_id, 'season': season, 'from': str(from_date), 'to': str(to_date)})
    if fixtures_data and fixtures_data.get('response'):
        st.session_state['fixtures'] = fixtures_data['response']
    else:
        st.session_state['fixtures'] = []

fixtures = st.session_state.get('fixtures', [])
if fixtures:
    fixture_options = {f"{f['fixture']['id']} - {f['teams']['home']['name']} vs {f['teams']['away']['name']}": f['fixture']['id'] for f in fixtures}
    selected = st.selectbox('Selecione fixture', list(fixture_options.keys()))
    fixture_id = fixture_options[selected]
    
    if st.button('Analisar'):
        fixture = get_fixture(fixture_id)
        if not fixture:
            st.error('Fixture não encontrada.')
        else:
            home_id = fixture['teams']['home']['id']
            away_id = fixture['teams']['away']['id']
            
            home_avgs = get_team_averages(home_id, season) or get_team_stats(home_id, league_id, season)
            away_avgs = get_team_averages(away_id, season) or get_team_stats(away_id, league_id, season)
            
            if home_avgs and away_avgs:
                # Cálculo Poisson simplificado para Over 0.5 HT, Over 1.5 FT, BTTS
                lam_home = home_avgs.get('avg_goals_for', 1.3) if isinstance(home_avgs, dict) else 1.3
                lam_away = away_avgs.get('avg_goals_against', 1.2) if isinstance(away_avgs, dict) else 1.2
                
                # Probabilidades
                probs = []
                for line in [0.5, 1.5, 2.5]:
                    p_over = sum(poisson_pmf(k, lam_home + lam_away) for k in range(int(line)+1, 10))
                    probs.append({'Linha': f'Over {line}', 'Probabilidade %': round(p_over*100, 1)})
                
                df = pd.DataFrame(probs)
                st.dataframe(df)
                
                # Filtro 75%
                high = df[df['Probabilidade %'] >= 75]
                if not high.empty:
                    st.write('Linhas com >=75%:', high)
                
                # CSV
                csv = df.to_csv(index=False)
                st.download_button('Baixar CSV', csv, 'probs.csv')
                
                # PDF
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font('Arial', size=12)
                for _, row in df.iterrows():
                    pdf.cell(0, 10, f"{row['Linha']}: {row['Probabilidade %']}%", ln=True)
                pdf_bytes = pdf.output(dest='S').encode('latin-1', errors='replace')
                st.download_button('Baixar PDF', pdf_bytes, 'report.pdf')
            else:
                st.warning('Dados insuficientes para cantos/cartões/HT.')
    else:
        st.info('Clique em Analisar para processar.')
else:
    st.info('Busque fixtures primeiro.')
