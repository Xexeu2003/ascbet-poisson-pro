import streamlit as st
import requests
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime
from scipy.stats import poisson

st.set_page_config(page_title="Analisador Premium asc.bet", layout="wide")

# PROTEÇÃO: Evita quebras caso os Secrets estejam vazios
API_FOOTBALL_KEY = st.secrets.get("API_KEY", None)

LIGAS = {
    71: "BRASIL: Série A", 72: "BRASIL: Série B", 73: "BRASIL: Série C",
    39: "INGLATERRA: Premier League", 40: "INGLATERRA: EFL Championship", 41: "INGLATERRA: EFL League One", 42: "INGLATERRA: EFL League Two",
    128: "ARGENTINA: Liga Profesional", 129: "ARGENTINA: Primera Nacional",
    253: "EUA: Major League Soccer (MLS)", 255: "EUA: USL Championship", 262: "MÉXICO: Liga MX",
    239: "COLÔMBIA: Primera A", 240: "COLÔMBIA: Primera B", 265: "CHILE: Primera División", 266: "CHILE: Primera B",
    268: "URUGUAI: Primera División", 269: "URUGUAI: Segunda División", 242: "PARAGUAI: Primera División", 243: "PARAGUAI: División Intermedia",
    271: "VENEZUELA: Liga FUTVE", 272: "VENEZUELA: Liga FUTVE 2", 281: "PERU: Liga 1", 282: "PERU: Liga 2",
    88: "HOLANDA: Eredivisie", 89: "HOLANDA: Eerste Divisie", 144: "BÉLGICA: Jupiler Pro League", 145: "BÉLGICA: Challenger Pro League",
    113: "SUÉCIA: Allsvenskan", 114: "SUÉCIA: Superettan", 119: "DINAMARCA: Superligaen", 120: "DINAMARCA: 1st Division", 121: "DINAMARCA: 2nd Division",
    244: "FINLÂNDIA: Veikkausliiga", 245: "FINLÂNDIA: Ykkösliiga", 246: "FINLÂNDIA: Kakkonen", 182: "ISLÂNDIA: Besta deild karla", 183: "ISLÂNDIA: 1. deild karla",
    106: "POLÔNIA: Ekstraklasa", 107: "POLÔNIA: I Liga", 108: "POLÔNIA: II Liga", 210: "CROÁCIA: HNL", 211: "CROÁCIA: Prva NL",
    78: "ALEMANHA: Bundesliga", 79: "ALEMANHA: 2. Bundesliga", 80: "ALEMANHA: 3. Liga", 81: "ALEMANHA: Regionalliga", 61: "FRANÇA: Ligue 1", 62: "FRANÇA: Ligue 2",
    140: "ESPANHA: La Liga", 141: "ESPANHA: La Liga 2", 94: "PORTUGAL: Primeira Liga", 95: "PORTUGAL: Segunda Liga",
    135: "ITÁLIA: Serie A", 136: "ITÁLIA: Serie B", 137: "ITÁLIA: Serie C", 307: "ARÁBIA SAUDITA: Saudi Pro League", 308: "ARÁBIA SAUDITA: Yelo League",
    203: "TURQUIA: Süper Lig", 204: "TURQUIA: TFF 1. Lig", 197: "GRÉCIA: Super League 1", 383: "ISRAEL: Ligat Ha'Al", 384: "ISRAEL: Liga Leumit",
    188: "AUSTRÁLIA: A-League", 98: "JAPÃO: J1 League", 99: "JAPÃO: J2 League", 169: "CHINA: Super League", 170: "CHINA: League One",
    292: "COREIA DO SUL: K League 1", 293: "COREIA DO SUL: K League 2", 278: "ÍNDIA: Indian Super League", 279: "ÍNDIA: I-League",
    124: "HUNGRIA: NB I", 125: "HUNGRIA: NB II", 207: "SUIÇA: Super League"
}

HEADERS = {'x-apisports-key': API_FOOTBALL_KEY if API_FOOTBALL_KEY else "", 'x-rapidapi-host': "v3.football.api-sports.io"}

# SOLUÇÃO DEFINITIVA PARA TELA BRANCA: Banco criado na RAM livre de travas de arquivos do Linux
if 'db_conn' not in st.session_state:
    st.session_state.db_conn = sqlite3.connect(':memory:', check_same_thread=False)
    cursor = st.session_state.db_conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS stats_times (team_id INTEGER, liga_id INTEGER, season INTEGER, gols_marcados_ht REAL, gols_sofridos_ht REAL, gols_marcados_ft REAL, gols_sofridos_ft REAL, cantos_media REAL, cartoes_media REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS historico_partidas (confronto TEXT, odd_ht REAL, odd_15ft REAL, odd_btts REAL)')
    st.session_state.db_conn.commit()

def buscar_stats_local(team_id, liga_id, season):
    try:
        cursor = st.session_state.db_conn.cursor()
        cursor.execute('SELECT gols_marcados_ht, gols_sofridos_ht, gols_marcados_ft, gols_sofridos_ft, cantos_media, cartoes_media FROM stats_times WHERE team_id=? AND liga_id=? AND season=?', (team_id, liga_id, season))
        row = cursor.fetchone()
        if row: return {'gols_marcados_ht': row[0], 'gols_sofridos_ht': row[1], 'gols_marcados_ft': row[2], 'gols_sofridos_ft': row[3], 'cantos_media': row[4], 'cartoes_media': row[5]}
    except: pass
    return None

def salvar_stats_local(team_id, liga_id, season, stats):
    try:
        cursor = st.session_state.db_conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO stats_times VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (team_id, liga_id, season, stats['gols_marcados_ht'], stats['gols_sofridos_ht'], stats['gols_marcados_ft'], stats['gols_sofridos_ft'], stats['cantos_media'], stats['cartoes_media']))
        st.session_state.db_conn.commit()
    except: pass

def calcular_probabilidades_poisson(lambda_casa, lambda_fora):
    prob_over_15 = (1 - (poisson.pmf(0, lambda_casa + lambda_fora) + poisson.pmf(1, lambda_casa + lambda_fora))) * 100
    prob_btts = (1 - poisson.pmf(0, lambda_casa)) * (1 - poisson.pmf(0, lambda_fora)) * 100
    return round(prob_over_15, 1), round(prob_btts, 1)

def obter_estatisticas_time_filtrado(liga_id, season, team_id):
    dados_locais = buscar_stats_local(team_id, liga_id, season)
    if dados_locais: return dados_locais
    dados_padrao = {'gols_marcados_ht': 0.6, 'gols_sofridos_ht': 0.5, 'gols_marcados_ft': 1.3, 'gols_sofridos_ft': 1.1, 'cantos_media': 5.0, 'cartoes_media': 2.2}
    if not API_FOOTBALL_KEY: return dados_padrao
    try:
        r = requests.get("https://api-sports.io", headers=HEADERS, params={'league': liga_id, 'season': season, 'team': team_id})
        if r.status_code != 200: return dados_padrao
        res = r.json().get('response', {})
        gols = res.get('goals', {})
        gols_m = float(gols.get('for', {}).get('average', {}).get('total', 1.3))
        gols_s = float(gols.get('against', {}).get('average', {}).get('total', 1.1))
        res_stats = {'gols_marcados_ht': gols_m * 0.45, 'gols_sofridos_ht': gols_s * 0.45, 'gols_marcados_ft': gols_m, 'gols_sofridos_ft': gols_s, 'cantos_media': float(res.get('corners', {}).get('for', {}).get('average', {}).get('total', 5.0)), 'cartoes_media': float(res.get('cards', {}).get('yellow', {}).get('total', {}).get('average', 2.0) or 2.0)}
        salvar_stats_local(team_id, liga_id, season, res_stats)
        return res_stats
    except: return dados_padrao

def buscar_jogos_e_projetar(ligas_ids, data_escolhida):
    data_formatada = data_escolhida.strftime("%Y-%m-%d")
    jogos, log = [], []
    if not API_FOOTBALL_KEY: return pd.DataFrame(), ["⚠️ Insira a chave nos Secrets."]
    for liga_id in ligas_ids:
        for season_temp in [data_escolhida.year, data_escolhida.year - 1]:
            try:
                r = requests.get("https://api-sports.io", headers=HEADERS, params={'league': liga_id, 'season': season_temp, 'date': data_formatada})
                if r.status_code == 200:
                    fixtures = r.json().get('response', [])
                    if len(fixtures) > 0:
                        log.append(f"✅ Encontrados {len(fixtures)} jogos")
                        for f in fixtures:
                            id_c, id_f = f['teams']['home']['id'], f['teams']['away']['id']
                            dt = datetime.fromisoformat(f['fixture']['date'].replace('Z',''))
                            s_c, s_f = obter_estatisticas_time_filtrado(liga_id, season_temp, id_c), obter_estatisticas_time_filtrado(liga_id, season_temp, id_f)
                            
                            lambda_ft_c = (s_c['gols_marcados_ft'] + s_f['gols_sofridos_ft']) / 2
                            lambda_ft_f = (s_f['gols_marcados_ft'] + s_c['gols_sofridos_ft']) / 2
                            lambda_ht_total = ((s_c['gols_marcados_ht'] + s_f['gols_sofridos_ht']) / 2) + ((s_f['gols_marcados_ht'] + s_c['gols_sofridos_ht']) / 2)
                            
                            p_over_15 = round((1 - (poisson.pmf(0, lambda_ft_c + lambda_ft_f) + poisson.pmf(1, lambda_ft_c + lambda_ft_f))) * 100, 1)
                            p_btts = round(((1 - poisson.pmf(0, lambda_ft_c)) * (1 - poisson.pmf(0, lambda_ft_f))) * 100, 1)
                            p_ht = round((1 - poisson.pmf(0, lambda_ht_total)) * 100, 1)
                            
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
    return pd.DataFrame(jogos), log

# --- RENDERS DA TELA ---
st.title("Analisador Profissional asc.bet - Cobertura Global")
if not API_FOOTBALL_KEY: st.info("🔑 O token `API_KEY` não está preenchido nos Secrets. Operando em modo offline.")

tab1, tab2 = st.tabs(["🔮 Projeções e Odds Justas", "🧪 Painel de Backtesting"])
with tab1:
    col1, col2 = st.columns(2)
    with col1: ligas_selecionadas = st.multiselect("1. Selecione as Ligas", options=list(LIGAS.keys()), format_func=lambda x: LIGAS[x])
