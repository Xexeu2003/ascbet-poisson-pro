import streamlit as pd
import streamlit as st
import requests
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime, timedelta
from scipy.stats import poisson

st.set_page_config(page_title="Analisador Premium asc.bet", layout="wide")

# Puxa a chave dos Secrets do Streamlit Cloud
API_FOOTBALL_KEY = st.secrets["API_KEY"]

LIGAS = {
    71: "BRASIL: Série A", 
    72: "BRASIL: Série B",
    73: "BRASIL: Série C",
    39: "INGLATERRA: Premier League",
    40: "INGLATERRA: EFL Championship",
    128: "ARGENTINA: Liga Profesional",
    129: "ARGENTINA: Primera Nacional",
    262: "MÉXICO: Liga MX",
    253: "EUA: Major League Soccer (MLS)"
}

HEADERS = {
    'x-apisports-key': API_FOOTBALL_KEY, 
    'x-rapidapi-host': "v3.football.api-sports.io"
}

# --- ARQUITETURA DE BANCO DE DADOS AVANÇADA ---
def inicializar_e_limpar_banco():
    conn = sqlite3.connect('analisador_asc_bet.db')
    cursor = conn.cursor()
    
    # Tabela 1: Estatísticas brutas dos times (Cache de chamadas da API)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats_times (
            team_id INTEGER,
            liga_id INTEGER,
            season INTEGER,
            gols_marcados_ht REAL, gols_sofridos_ht REAL,
            gols_marcados_ft REAL, gols_sofridos_ft REAL,
            cantos_media REAL, cartoes_media REAL,
            data_registro DATE DEFAULT (date('now')),
            PRIMARY KEY (team_id, liga_id, season)
        )
    ''')
    
    # Tabela 2: Histórico de partidas já calculadas (Consulta offline retroativa)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_partidas (
            data_jogo TEXT,
            liga_id INTEGER,
            liga_nome TEXT,
            confronto TEXT,
            hora TEXT,
            prob_05_ht REAL, odd_ht REAL,
            prob_15_ft REAL, odd_15ft REAL,
            prob_btts REAL, odd_btts REAL,
            prob_cantos REAL, prob_cartoes REAL,
            data_calculo DATE DEFAULT (date('now'))
        )
    ''')
    
    # Rotina de Limpeza Automática: Remove registros com mais de 30 dias
    data_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    cursor.execute("DELETE FROM stats_times WHERE data_registro < ?", (data_limite,))
    cursor.execute("DELETE FROM historico_partidas WHERE data_calculo < ?", (data_limite,))
    
    conn.commit()
    conn.close()

# Funções de manipulação do Banco Local
def buscar_stats_local(team_id, liga_id, season):
    conn = sqlite3.connect('analisador_asc_bet.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT gols_marcados_ht, gols_sofridos_ht, gols_marcados_ft, gols_sofridos_ft, cantos_media, cartoes_media 
        FROM stats_times WHERE team_id=? AND liga_id=? AND season=?
    ''', (team_id, liga_id, season))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'gols_marcados_ht': row[0], 'gols_sofridos_ht': row[1],
            'gols_marcados_ft': row[2], 'gols_sofridos_ft': row[3],
            'cantos_media': row[4], 'cartoes_media': row[5]
        }
    return None

def salvar_stats_local(team_id, liga_id, season, stats):
    conn = sqlite3.connect('analisador_asc_bet.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO stats_times 
        (team_id, liga_id, season, gols_marcados_ht, gols_sofridos_ht, gols_marcados_ft, gols_sofridos_ft, cantos_media, cartoes_media, data_registro)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))
    ''', (team_id, liga_id, season, stats['gols_marcados_ht'], stats['gols_sofridos_ht'], 
          stats['gols_marcados_ft'], stats['gols_sofridos_ft'], stats['cantos_media'], stats['cartoes_media']))
    conn.commit()
    conn.close()

def buscar_jogos_calculados_local(ligas_ids, data_formatada):
    conn = sqlite3.connect('analisador_asc_bet.db')
    # Gera placeholders (?,?,?) dinâmicos conforme a quantidade de ligas selecionadas
    placeholders = ','.join('?' for _ in ligas_ids)
    query = f'''
        SELECT data_jogo, liga_nome, confronto, hora, prob_05_ht, odd_ht, prob_15_ft, odd_15ft, prob_btts, odd_btts, prob_cantos, prob_cartoes
        FROM historico_partidas WHERE data_jogo = ? AND liga_id IN ({placeholders})
    '''
    params = [data_formatada] + list(ligas_ids)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    # Renomeia colunas para manter o padrão visual do DataFrame original do app
    if not df.empty:
        df.columns = ["Data", "Liga", "Confronto", "Hora", "0.5 HT (%)", "Odd HT", "1.5 FT (%)", "Odd 1.5FT", "BTTS (%)", "Odd BTTS", "Over 8.5 Cantos (%)", "Over 4.5 Cartões (%)"]
    return df

def salvar_jogos_calculados_local(jogos_lista):
    conn = sqlite3.connect('analisador_asc_bet.db')
    cursor = conn.cursor()
    for j in jogos_lista:
        cursor.execute('''
            INSERT INTO historico_partidas 
            (data_jogo, liga_id, liga_nome, confronto, hora, prob_05_ht, odd_ht, prob_15_ft, odd_15ft, prob_btts, odd_btts, prob_cantos, prob_cartoes, data_calculo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))
        ''', (j['data_jogo'], j['liga_id'], j['Liga'], j['Confronto'], j['Hora'], j['0.5 HT (%)'], j['Odd HT'], j['1.5 FT (%)'], j['Odd 1.5FT'], j['BTTS (%)'], j['Odd BTTS'], j['Over 8.5 Cantos (%)'], j['Over 4.5 Cartões (%)']))
    conn.commit()
    conn.close()

# Inicializa o banco e roda o expurgo de dados antigos
inicializar_e_limpar_banco()

# --- CÁLCULOS E INFERÊNCIAS MATEMÁTICAS ---
def calcular_probabilidades_poisson(lambda_casa, lambda_fora):
    prob_0_gols = poisson.pmf(0, lambda_casa + lambda_fora)
    prob_1_gol = poisson.pmf(1, lambda_casa + lambda_fora)
    prob_over_15 = (1 - (prob_0_gols + prob_1_gol)) * 100
    
    prob_c_zero = poisson.pmf(0, lambda_casa)
    prob_f_zero = poisson.pmf(0, lambda_fora)
    prob_btts = (1 - prob_c_zero) * (1 - prob_f_zero) * 100
    return round(prob_over_15, 1), round(prob_btts, 1)

def calcular_mercado_acumulado(lambda_total, linha):
    prob_under_ou_igual = poisson.cdf(int(linha), lambda_total)
    prob_over = (1 - prob_under_ou_igual) * 100
    return round(prob_over, 1)

def calcular_odd_justa(probabilidade):
    if probabilidade <= 0: return 99.0
    return round(100 / probabilidade, 2)

# --- REQUISIÇÕES DA API ---
def obter_estatisticas_time_filtrado(liga_id, season, team_id, log_list):
    dados_locais = buscar_stats_local(team_id, liga_id, season)
    if dados_locais:
        log_list.append(f"📦 [Banco Local] Estatísticas do Time {team_id} carregadas.")
        return dados_locais

    url = "https://api-sports.io"
    params = {'league': liga_id, 'season': season, 'team': team_id}
    dados_padrao = {'gols_marcados_ht': 0.6, 'gols_sofridos_ht': 0.5, 'gols_marcados_ft': 1.3, 'gols_sofridos_ft': 1.1, 'cantos_media': 5.0, 'cartoes_media': 2.2}
    
    try:
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code == 429 or "requests" in r.text.lower():
            st.error("🚨 Limite diário de requisições esgotado na API-Football!")
            return dados_padrao
        if r.status_code != 200: return dados_padrao
        
        res = r.json()
        if "errors" in res and "requests" in str(res["errors"]).lower():
            st.error("🚨 Limite de chamadas estourado no plano da API!")
            return dados_padrao
            
        res_data = res.get('response', {})
        gols = res_data.get('goals', {})
        gols_marcados_ft = float(gols.get('for', {}).get('average', {}).get('total', 1.3))
        gols_sofridos_ft = float(gols.get('against', {}).get('average', {}).get('total', 1.1))
        
        resultado_stats = {
            'gols_marcados_ht': gols_marcados_ft * 0.45, 'gols_sofridos_ht': gols_sofridos_ft * 0.45,
            'gols_marcados_ft': gols_marcados_ft, 'gols_sofridos_ft': gols_sofridos_ft,
            'cantos_media': float(res_data.get('corners', {}).get('for', {}).get('average', {}).get('total', 5.0)),
            'cartoes_media': float(res_data.get('cards', {}).get('yellow', {}).get('total', {}).get('average', 2.0) or 2.0)
        }
        salvar_stats_local(team_id, liga_id, season, resultado_stats)
        return resultado_stats
    except:
        return dados_padrao

def buscar_jogos_e_projetar(ligas_ids, data_escolhida):
    data_formatada = data_escolhida.strftime("%Y-%m-%d")
    
    # PASSO 1: Tenta resgatar os confrontos inteiros já calculados no banco local
    df_local = buscar_jogos_calculated_local(ligas_ids, data_formatada)
    if not df_local.empty:
        return df_local, [f"🚀 [Modo Offline] Exibindo {len(df_local)} jogos processados localmente em buscas anteriores. Nenhuma requisição consumida!"]

    # PASSO 2: Se não existirem no banco, faz a busca na API web externa
    jogos = []
    log = []
    ano_atual = data_escolhida.year
    temporadas_para_buscar = [ano_atual, ano_atual - 1]
    
    for liga_id in ligas_ids:
        for season_temp in temporadas_para_buscar:
            url = "https://api-sports.io"
            params = {'league': liga_id, 'season': season_temp, 'date': data_formatada}
            try:
                r = requests.get(url, headers=HEADERS, params=params)
                if r.status_code == 429 or "requests" in r.text.lower():
                    st.error("🚨 Limite diário de requisições atingido ao buscar rodada!")
                    break
                    
                if r.status_code == 200:
                    res_json = r.json()
                    if "errors" in res_json and "requests" in str(res_json["errors"]).lower():
                        st.error("🚨 Limite de requisições excedido no plano da API!")
                        break
                        
                    fixtures = res_json.get('response', [])
                    if len(fixtures) > 0:
