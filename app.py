import streamlit as st
import requests
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime
from scipy.stats import poisson

# Configuração da página do Streamlit
st.set_page_config(page_title="Analisador Premium asc.bet", layout="wide", page_icon="📊")

# --- GERENCIAMENTO DE CHAVE DA API PRO CORRETA ---
st.sidebar.title("Configurações de Acesso PRO")
chave_padrao = st.secrets.get("API_KEY", "")
API_FOOTBALL_KEY = st.sidebar.text_input("Sua Chave API-Football PRO:", value=chave_padrao, type="password")

# DICIONÁRIO EXPANDIDO COM TODAS AS LIGAS SOLICITADAS (IDs OFICIAIS API-FOOTBALL PRO)
LIGAS = {
    # Brasil
    71: "BRASIL: Série A", 
    72: "BRASIL: Série B", 
    73: "BRASIL: Série C",
    # Croácia
    210: "CROÁCIA: HNL", 
    211: "CROÁCIA: Prva NL",
    # Austrália
    188: "AUSTRÁLIA: A-League Men",
    # Japão
    196: "JAPÃO: J1 League", 
    197: "JAPÃO: J2 League",
    # China
    169: "CHINA: Superliga Chinesa (CSL)", 
    170: "CHINA: China League One",
    # Coreia do Sul
    292: "COREIA DO SUL: K League 1", 
    293: "COREIA DO SUL: K League 2",
    # Hungria
    271: "HUNGRIA: NB I", 
    272: "HUNGRIA: NB II",
    # Suíça
    207: "SUÍÇA: Swiss Super League",
    # Turquia
    203: "TURQUIA: Süper Lig", 
    204: "TURQUIA: TFF 1. Lig",
    # Grécia
    197: "GRÉCIA: Super League 1",
    # Israel
    243: "ISRAEL: Ligat Ha'Al", 
    244: "ISRAEL: Liga Leumit",
    # Alemanha
    78: "ALEMANHA: Bundesliga", 
    79: "ALEMANHA: Bundesliga 2", 
    80: "ALEMANHA: Bundesliga 3", 
    81: "ALEMANHA: Regionalliga",
    # Inglaterra
    39: "INGLATERRA: Premier League", 
    40: "INGLATERRA: EFL Championship", 
    41: "INGLATERRA: EFL League One", 
    42: "INGLATERRA: EFL League Two",
    # França
    61: "FRANÇA: Ligue 1", 
    62: "FRANÇA: Ligue 2",
    # Espanha
    140: "ESPANHA: La Liga", 
    141: "ESPANHA: La Liga 2",
    # Portugal
    94: "PORTUGAL: Primeira Liga", 
    95: "PORTUGAL: Segunda Liga",
    # Itália
    135: "ITÁLIA: Serie A", 
    136: "ITÁLIA: Serie B", 
    137: "ITÁLIA: Serie C",
    # Índia
    323: "ÍNDIA: Indian Super League (ISL)", 
    324: "ÍNDIA: I-League",
    # Arábia Saudita
    307: "ARÁBIA SAUDITA: Saudi Pro League", 
    308: "ARÁBIA SAUDITA: Yelo League (1st Div)",
    # Holanda
    88: "HOLANDA: Eredivisie",
    89: "HOLANDA: Eerste Divisie",
    # Finlândia
    247: "FINLÂNDIA: Veikkausliiga",
    248: "FINLÂNDIA: Ykkönen",
    # Dinamarca
    119: "DINAMARCA: Superliga",
    120: "DINAMARCA: 1st Division",
    # Islândia
    352: "ISLÂNDIA: Besta deild karla",
    353: "ISLÂNDIA: 1. deild"
}

# Cabeçalhos ajustados para o Servidor de Produção PRO Direto
HEADERS = {
    'x-apisports-key': API_FOOTBALL_KEY
}

# --- BANCO DE DADOS LOCAL ---
if 'db_conn' not in st.session_state:
    st.session_state.db_conn = sqlite3.connect('asc_bet_dados_v2.db', check_same_thread=False)
    cursor = st.session_state.db_conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS historico_partidas 
                      (confronto TEXT PRIMARY KEY, odd_ht REAL, odd_15ft REAL, odd_25ft REAL, odd_btts REAL)''')
    st.session_state.db_conn.commit()

# --- FUNÇÕES DE CÁLCULO E INTEGRAL DE POISSON ---
@st.cache_data(ttl=86400)
def obter_estatisticas_time_filtrado(liga_id, season, team_id, _headers):
    try:
        url = "https://api-sports.io"
        r = requests.get(url, headers=_headers, params={'league': liga_id, 'season': season, 'team': team_id})
        if r.status_code == 200:
            res = r.json().get('response', {})
            gols = res.get('goals', {})
            
            gols_m = float(gols.get('for', {}).get('average', {}).get('total', 1.3) or 1.3)
            gols_s = float(gols.get('against', {}).get('average', {}).get('total', 1.1) or 1.1)
            
            cantos_media = res.get('corners', {}).get('average', {}).get('total', 5.0)
            cantos = float(cantos_media if cantos_media is not None else 5.0)
            
            cartoes_media = res.get('cards', {}).get('yellow', {}).get('average', 2.0)
            cartoes = float(cartoes_media if cartoes_media is not None else 2.2)
            
            return {'gols_m': gols_m, 'gols_s': gols_s, 'cantos': cantos, 'cartoes': cartoes}
    except:
        pass
    return {'gols_m': 1.3, 'gols_s': 1.1, 'cantos': 5.0, 'cartoes': 2.2}

def calcular_probabilidades_poisson(s_c, s_f):
    l_ft_c = (s_c['gols_m'] + s_f['gols_s']) / 2
    l_ft_f = (s_f['gols_m'] + s_c['gols_s']) / 2
    l_ht_total = (l_ft_c * 0.45) + (l_ft_f * 0.45)
    
    p_ht = round((1 - poisson.pmf(0, l_ht_total)) * 100, 1)
    p_over_15 = round((1 - (poisson.pmf(0, l_ft_c + l_ft_f) + poisson.pmf(1, l_ft_c + l_ft_f))) * 100, 1)
    
    prob_0_gols = poisson.pmf(0, l_ft_c + l_ft_f)
    prob_1_gol = poisson.pmf(1, l_ft_c + l_ft_f)
    prob_2_gols = poisson.pmf(2, l_ft_c + l_ft_f)
    p_over_25 = round((1 - (prob_0_gols + prob_1_gol + prob_2_gols)) * 100, 1)
    
    p_btts = round(((1 - poisson.pmf(0, l_ft_c)) * (1 - poisson.pmf(0, l_ft_f))) * 100, 1)
    p_cantos_85 = round((1 - poisson.cdf(8, s_c['cantos'] + s_f['cantos'])) * 100, 1)
    p_cartoes_45 = round((1 - poisson.cdf(4, s_c['cartoes'] + s_f['cartoes'])) * 100, 1)
    
    odd_ht = round(100/p_ht, 2) if p_ht > 0 else 99.0
    odd_15 = round(100/p_over_15, 2) if p_over_15 > 0 else 99.0
    odd_25 = round(100/p_over_25, 2) if p_over_25 > 0 else 99.0
    odd_bt = round(100/p_btts, 2) if p_btts > 0 else 99.0
    
    return {
        "p_ht": p_ht, "odd_ht": odd_ht,
        "p_over_15": p_over_15, "odd_15": odd_15,
        "p_over_25": p_over_25, "odd_25": odd_25,
        "p_btts": p_btts, "odd_bt": odd_bt,
        "p_cantos_85": p_cantos_85, "p_cartoes_45": p_cartoes_45
    }

def processar_jogos_da_liga(liga_id, data_escolhida, headers):
    data_formatada = data_escolhida.strftime("%Y-%m-%d")
    jogos = []
    ano_atual = data_escolhida.year
    cursor = st.session_state.db_conn.cursor()
    
    for season_temp in [ano_atual, ano_atual - 1]:
        try:
            url = "https://api-sports.io"
            r = requests.get(url, headers=headers, params={'league': liga_id, 'season': season_temp, 'date': data_formatada})
            
            if r.status_code == 200:
                fixtures = r.json().get('response', [])
                if len(fixtures) > 0:
                    for f in fixtures:
                        id_c, id_f = f['teams']['home']['id'], f['teams']['away']['id']
                        nome_c, name_f = f['teams']['home']['name'], f['teams']['away']['name']
                        dt_str = f['fixture']['date']
                        hora_formatada = dt_str[11:16] if len(dt_str) > 16 else "00:00"
                        
                        s_c = obter_estatisticas_time_filtrado(liga_id, season_temp, id_c, headers)
                        s_f = obter_estatisticas_time_filtrado(liga_id, season_temp, id_f, headers)
                        
                        calc = calcular_probabilidades_poisson(s_c, s_f)
                        conf_nome = f"{nome_c} x {name_f}"
                        
                        cursor.execute('INSERT OR REPLACE INTO historico_partidas VALUES (?, ?, ?, ?, ?)', 
                                       (conf_nome, calc['odd_ht'], calc['odd_15'], calc['odd_25'], calc['odd_bt']))
                        st.session_state.db_conn.commit()
                        
                        jogos.append({
                            "Data": data_escolhida.strftime("%d/%m"),
                            "Liga": LIGAS[liga_id],
                            "Confronto": conf_nome,
                            "Hora": hora_formatada,
                            "0.5 HT (%)": calc['p_ht'], "Odd HT": calc['odd_ht'],
                            "1.5 FT (%)": calc['p_over_15'], "Odd 1.5FT": calc['odd_15'],
                            "2.5 FT (%)": calc['p_over_25'], "Odd 2.5FT": calc['odd_25'],
                            "BTTS (%)": calc['p_btts'], "Odd BTTS": calc['odd_bt'],
                            "Over 8.5 Cantos (%)": calc['p_cantos_85'],
                            "Over 4.5 Cartões (%)": calc['p_cartoes_45']
                        })
                    break
        except Exception as e:
            st.error(f"Erro na conexão com os dados da liga: {e}")
            
    return pd.DataFrame(jogos)

# --- CORPO DA INTERFACE VISUAL ---
st.title("Analisador Profissional asc.bet - Cobertura Global")

if not API_FOOTBALL_KEY:
    st.error("🚨 Chave de API ausente ou inválida. Insira sua chave PRO na barra lateral esquerda para ativar o app.")
else:
    tab_individual, tab_multiplas, tab_backtest = st.tabs([
        "🔬 Análise Individual (Uma Liga por Vez)", 
        "🔮 Projeções em Massa (Várias Ligas)", 
        "🧪 Painel de Backtesting"
    ])

    # --- ABA 1: ANÁLISE INDIVIDUAL ---
    with tab_individual:
        st.subheader("Análise Avançada e Cirúrgica por Competição")
        col1, col2 = st.columns(2)
        with col1:
            liga_unica = st.selectbox(
                "Selecione a Liga Desejada", 
                options=sorted(list(LIGAS.keys()), key=lambda x: LIGAS[x]), 
                format_func=lambda x: LIGAS[x]
            )
        with col2:
            data_unica = st.date_input("Data dos Confrontos", datetime.now(), key="data_unica")
            
        if st.button("📊 PROJETAR JOGOS DA LIGA", type="primary"):
            with st.spinner(f"Coletando dados e aplicando Poisson para {LIGAS[liga_unica]}..."):
                df_liga = processar_jogos_da_liga(liga_unica, data_unica, HEADERS)
                
                if df_liga.empty:
                    st.info(f"Sem partidas ativas localizadas para {LIGAS[liga_unica]} nesta data.")
                else:
                    st.success(f"Sucesso! {len(df_liga)} partidas encontradas.")
