import streamlit as st
import requests
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime
from scipy.stats import poisson

st.set_page_config(page_title="Analisador Premium asc.bet", layout="wide")

API_FOOTBALL_KEY = st.secrets.get("API_KEY", None)

LIGAS = {
    71: "BRASIL: Série A", 72: "BRASIL: Série B", 73: "BRASIL: Série C",
    39: "INGLATERRA: Premier League", 40: "INGLATERRA: EFL Championship",
    128: "ARGENTINA: Liga Profesional", 129: "ARGENTINA: Primera Nacional",
    253: "EUA: Major League Soccer (MLS)", 262: "MÉXICO: Liga MX"
}

# CORREÇÃO CRÍTICA: Host atualizado para validar os acessos do plano gratuito correto
HEADERS = {
    'x-rapidapi-key': API_FOOTBALL_KEY if API_FOOTBALL_KEY else "",
    'x-rapidapi-host': "api-football-v1.p.rapidapi.io"
}

if 'db_conn' not in st.session_state:
    st.session_state.db_conn = sqlite3.connect(':memory:', check_same_thread=False)
    cursor = st.session_state.db_conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS stats_times (team_id INTEGER, liga_id INTEGER, season INTEGER, gols_marcados_ht REAL, gols_sofridos_ht REAL, gols_marcados_ft REAL, gols_sofridos_ft REAL, cantos_media REAL, cartoes_media REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS historico_partidas (confronto TEXT, odd_ht REAL, odd_15ft REAL, odd_btts REAL)')
    st.session_state.db_conn.commit()

def obter_estatisticas_time_filtrado(liga_id, season, team_id):
    dados_padrao = {'gols_marcados_ht': 0.6, 'gols_sofridos_ht': 0.5, 'gols_marcados_ft': 1.3, 'gols_sofridos_ft': 1.1, 'cantos_media': 5.0, 'cartoes_media': 2.2}
    if not API_FOOTBALL_KEY: return dados_padrao
    try:
        r = requests.get("https://rapidapi.io", headers=HEADERS, params={'league': liga_id, 'season': season, 'team': team_id})
        if r.status_code != 200: return dados_padrao
        res = r.json().get('response', {})
        gols = res.get('goals', {})
        gols_m = float(gols.get('for', {}).get('average', {}).get('total', 1.3))
        gols_s = float(gols.get('against', {}).get('average', {}).get('total', 1.1))
        return {'gols_marcados_ht': gols_m * 0.45, 'gols_sofridos_ht': gols_s * 0.45, 'gols_marcados_ft': gols_m, 'gols_sofridos_ft': gols_s, 'cantos_media': float(res.get('corners', {}).get('for', {}).get('average', {}).get('total', 5.0)), 'cartoes_media': float(res.get('cards', {}).get('yellow', {}).get('total', {}).get('average', 2.0) or 2.0)}
    except: return dados_padrao

def buscar_jogos_e_projetar(ligas_ids, data_escolhida):
    data_formatada = data_escolhida.strftime("%Y-%m-%d")
    jogos = []
    if not API_FOOTBALL_KEY: return pd.DataFrame(), ["⚠️ Chave ausente."]
    ano_atual = data_escolhida.year
    
    for liga_id in ligas_ids:
        for season_temp in [ano_atual, ano_atual - 1]:
            try:
                r = requests.get("https://rapidapi.io", headers=HEADERS, params={'league': liga_id, 'season': season_temp, 'date': data_formatada})
                if r.status_code == 200:
                    fixtures = r.json().get('response', [])
                    if len(fixtures) > 0:
                        for f in fixtures:
                            id_c, id_f = f['teams']['home']['id'], f['teams']['away']['id']
                            dt = datetime.fromisoformat(f['fixture']['date'].replace('Z',''))
                            s_c, s_f = obter_estatisticas_time_filtrado(liga_id, season_temp, id_c), obter_estatisticas_time_filtrado(liga_id, season_temp, id_f)
                            
                            l_ft_c = (s_c['gols_marcados_ft'] + s_f['gols_sofridos_ft']) / 2
                            l_ft_f = (s_f['gols_marcados_ft'] + s_c['gols_sofridos_ft']) / 2
                            l_ht_total = ((s_c['gols_marcados_ht'] + s_f['gols_sofridos_ht']) / 2) + ((s_f['gols_marcados_ht'] + s_c['gols_sofridos_ht']) / 2)
                            
                            p_over_15 = round((1 - (poisson.pmf(0, l_ft_c + l_ft_f) + poisson.pmf(1, l_ft_c + l_ft_f))) * 100, 1)
                            p_btts = round(((1 - poisson.pmf(0, l_ft_c)) * (1 - poisson.pmf(0, l_ft_f))) * 100, 1)
                            p_ht = round((1 - poisson.pmf(0, l_ht_total)) * 100, 1)
                            
                            conf_nome = f"{f['teams']['home']['name']} x {f['teams']['away']['name']}"
                            odd_h = round(100/p_ht, 2) if p_ht > 0 else 99.0
                            odd_15 = round(100/p_over_15, 2) if p_over_15 > 0 else 99.0
                            odd_bt = round(100/p_btts, 2) if p_btts > 0 else 99.0
                            
                            cursor = st.session_state.db_conn.cursor()
                            cursor.execute('INSERT OR REPLACE INTO historico_partidas VALUES (?, ?, ?, ?)', (conf_nome, odd_h, odd_15, odd_bt))
                            st.session_state.db_conn.commit()
                            
                            jogos.append({
                                "Data": dt.strftime("%d/%m"), "Liga": LIGAS[liga_id], "Confronto": conf_nome, "Hora": dt.strftime("%H:%M"),
                                "0.5 HT (%)": p_ht, "Odd HT": odd_h, "1.5 FT (%)": p_over_15, "Odd 1.5FT": odd_15, "BTTS (%)": p_btts, "Odd BTTS": odd_bt,
                                "Over 8.5 Cantos (%)": round((1 - poisson.cdf(8, s_c['cantos_media'] + s_f['cantos_media'])) * 100, 1),
                                "Over 4.5 Cartões (%)": round((1 - poisson.cdf(4, s_c['cartoes_media'] + s_f['cartoes_media'])) * 100, 1)
                            })
                        break
            except: continue
    return pd.DataFrame(jogos), []

st.title("Analisador Profissional asc.bet - Cobertura Global")

tab1, tab2 = st.tabs(["🔮 Projeções e Odds Justas", "🧪 Painel de Backtesting"])
with tab1:
    col1, col2 = st.columns(2)
    with col1: ligas_selecionadas = st.multiselect("1. Selecione as Ligas", options=list(LIGAS.keys()), format_func=lambda x: LIGAS[x])
    with col2: data_escolhida = st.date_input("2. Data da Rodada", datetime.now())
        
    if st.button("📊 PRECIFICAR JOGOS", type="primary"):
        if not ligas_selecionadas: st.warning("Selecione ao menos uma liga.")
        else:
            with st.spinner("Processando dados e aplicando Poisson..."):
                df_res, _ = buscar_jogos_e_projetar(ligas_selecionadas, data_escolhida)
                if df_res.empty: st.info("Nenhum jogo localizado para esta data.")
                else: st.dataframe(df_res, use_container_width=True)

with tab2:
    st.subheader("Simulação de Validação Estatística")
    arquivo_upload = st.file_uploader("Escolha seu arquivo CSV ou XLSX", type=["csv", "xlsx"])
