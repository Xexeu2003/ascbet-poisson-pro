import streamlit as st
import requests
import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime, timedelta
from scipy.stats import poisson

st.set_page_config(page_title="Analisador Premium asc.bet", layout="wide")

# PROTEÇÃO AVANÇADA: st.secrets.get() evita que o Streamlit quebre se o arquivo de secrets não existir
API_FOOTBALL_KEY = st.secrets.get("API_KEY", None)

# Mapeamento Estruturado das Ligas Oficiais
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
NOME_BANCO = 'analisador_asc_bet.db'

def inicializar_e_limpar_banco():
    try:
        conn = sqlite3.connect(NOME_BANCO)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS stats_times (team_id INTEGER, liga_id INTEGER, season INTEGER, gols_marcados_ht REAL, gols_sofridos_ht REAL, gols_marcados_ft REAL, gols_sofridos_ft REAL, cantos_media REAL, cartoes_media REAL, data_registro TEXT, PRIMARY KEY (team_id, liga_id, season))')
        cursor.execute('CREATE TABLE IF NOT EXISTS historico_partidas (data_jogo TEXT, liga_id INTEGER, liga_nome TEXT, confronto TEXT, hora TEXT, prob_05_ht REAL, odd_ht REAL, prob_15_ft REAL, odd_15ft REAL, prob_btts REAL, odd_btts REAL, prob_cantos REAL, prob_cartoes REAL, data_calculo TEXT)')
        data_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        cursor.execute("DELETE FROM stats_times WHERE data_registro < ?", (data_limite,))
        cursor.execute("DELETE FROM historico_partidas WHERE data_calculo < ?", (data_limite,))
        conn.commit()
        conn.close()
    except: pass

def buscar_stats_local(team_id, liga_id, season):
    try:
        conn = sqlite3.connect(NOME_BANCO)
        cursor = conn.cursor()
        cursor.execute('SELECT gols_marcados_ht, gols_sofridos_ht, gols_marcados_ft, gols_sofridos_ft, cantos_media, cartoes_media FROM stats_times WHERE team_id=? AND liga_id=? AND season=?', (team_id, liga_id, season))
        row = cursor.fetchone()
        conn.close()
        if row: return {'gols_marcados_ht': row[0], 'gols_sofridos_ht': row[1], 'gols_marcados_ft': row[2], 'gols_sofridos_ft': row[3], 'cantos_media': row[4], 'cartoes_media': row[5]}
    except: pass
    return None

def salvar_stats_local(team_id, liga_id, season, stats):
    try:
        conn = sqlite3.connect(NOME_BANCO)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO stats_times VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (team_id, liga_id, season, stats['gols_marcados_ht'], stats['gols_sofridos_ht'], stats['gols_marcados_ft'], stats['gols_sofridos_ft'], stats['cantos_media'], stats['cartoes_media'], datetime.now().strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
    except: pass

def buscar_jogos_calculados_local(ligas_ids, data_formatada):
    try:
        conn = sqlite3.connect(NOME_BANCO)
        placeholders = ','.join('?' for _ in ligas_ids)
        df = pd.read_sql_query(f'SELECT data_jogo, liga_nome, confronto, hora, prob_05_ht, odd_ht, prob_15_ft, odd_15ft, prob_btts, odd_btts, prob_cantos, prob_cartoes FROM historico_partidas WHERE data_jogo = ? AND liga_id IN ({placeholders})', conn, params=[data_formatada] + list(ligas_ids))
        conn.close()
        if not df.empty: df.columns = ["Data", "Liga", "Confronto", "Hora", "0.5 HT (%)", "Odd HT", "1.5 FT (%)", "Odd 1.5FT", "BTTS (%)", "Odd BTTS", "Over 8.5 Cantos (%)", "Over 4.5 Cartões (%)"]
        return df
    except: return pd.DataFrame()

def salvar_jogos_calculados_local(jogos_lista):
    try:
        conn = sqlite3.connect(NOME_BANCO)
        cursor = conn.cursor()
        hoje = datetime.now().strftime('%Y-%m-%d')
        for j in jogos_lista: cursor.execute('INSERT INTO historico_partidas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (j['data_jogo'], j['liga_id'], j['Liga'], j['Confronto'], j['Hora'], j['0.5 HT (%)'], j['Odd HT'], j['1.5 FT (%)'], j['Odd 1.5FT'], j['BTTS (%)'], j['Odd BTTS'], j['Over 8.5 Cantos (%)'], j['Over 4.5 Cartões (%)'], hoje))
        conn.commit()
        conn.close()
    except: pass

inicializar_e_limpar_banco()

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
    df_local = buscar_jogos_calculados_local(ligas_ids, data_formatada)
    if not df_local.empty: return df_local, ["🚀 Exibindo dados de cache local."]
    
    jogos, log = [], []
    if not API_FOOTBALL_KEY: return pd.DataFrame(), ["⚠️ Insira a chave nos Secrets."]
    
    for liga_id in ligas_ids:
        for season_temp in [data_escolhida.year, data_escolhida.year - 1]:
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
