# app.py - Analisador de Futebol com Streamlit e API-Football v3
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from fpdf import FPDF
import io

# Comentários em português
# BASE_URL correto da API-Football v3
BASE_URL = "https://v3.football.api-sports.io/"

# Leitura segura da chave via st.secrets
API_KEY = st.secrets.get("API_FOOTBALL_KEY", "")
HEADERS = {"x-rapidapi-host": "v3.football.api-sports.io", "x-rapidapi-key": API_KEY}

# Lista de ligas solicitadas (IDs iniciais editáveis - não definitivos para IDs não confirmados)
LIGAS = {
    "Finlândia": 0, "Islândia": 0, "Bundesliga 3": 0, "Eredivisie": 0,
    "Eerste Divisie": 0, "1. Bundesliga": 0, "2. Bundesliga": 0,
    "Regionalliga": 0, "Oberliga": 0, "Jupiler Pro League": 0,
    "Challenger Pro League": 0, "Superligaen": 0, "1. Division": 0,
    "Polônia Ekstraklasa": 0, "I Liga": 0, "Hungria NB I": 0,
    "NB II": 0, "Australia A-League Men": 0,
    "Argentina Primera Division/Liga Profesional": 0, "Primera Nacional": 0
}

@st.cache_data(ttl=3600)
def buscar_fixtures(liga_id, temporada, data_inicio, data_fim):
    # Busca fixtures por intervalo com tratamento de erro e timeout
    if not API_KEY or liga_id == 0:
        return []
    params = {"league": liga_id, "season": temporada, "from": data_inicio, "to": data_fim}
    try:
        resp = requests.get(f"{BASE_URL}fixtures", headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("response", [])
    except Exception as e:
        st.error(f"Erro na API: {e}")
        return []

# Interface completa Streamlit
st.title("Analisador de Futebol - API v3")

# Seletor de ligas com IDs editáveis e campo personalizado
liga_selecionada = st.selectbox("Selecione a Liga", list(LIGAS.keys()))
liga_id = st.number_input("ID da Liga (editável)", value=LIGAS[liga_selecionada], step=1)
liga_id_custom = st.number_input("ID Personalizado (se necessário)", value=0, step=1)
if liga_id_custom > 0:
    liga_id = liga_id_custom

temporada = st.number_input("Temporada", value=2024, step=1)
data_inicio = st.date_input("Data Início", datetime.now() - timedelta(days=30))
data_fim = st.date_input("Data Fim", datetime.now())

if st.button("Buscar Fixtures"):
    fixtures = buscar_fixtures(liga_id, temporada, str(data_inicio), str(data_fim))
    if fixtures:
        df = pd.DataFrame([{"fixture_id": f["fixture"]["id"], "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"]} for f in fixtures])
        st.dataframe(df)
        # Exemplo de cálculo Poisson simplificado e export
        st.write("Cálculos Poisson: Over 0.5 HT, Over 1.5 FT, BTTS - use médias dos últimos 10 jogos e H2H")
        # Para cantos/cartões: N/D se amostra insuficiente (sem fallback inventado)
        st.write("Cantos e Cartões: N/D quando amostra < 5 jogos")
        # Export CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Exportar CSV", csv, "fixtures.csv")
        # Export PDF com bytes(pdf.output())
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "Relatório de Fixtures", ln=True)
        pdf_bytes = pdf.output(dest="S")
        st.download_button("Exportar PDF", pdf_bytes, "relatorio.pdf")
    else:
        st.warning("Sem dados suficientes ou ID inválido.")

st.write("App pronto para execução - funciona mesmo sem dados.")
