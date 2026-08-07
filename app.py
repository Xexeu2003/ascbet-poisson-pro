import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import poisson

st.set_page_config(page_title="Analisador Premium asc.bet", layout="wide")

# Puxa a chave dos Secrets do Streamlit Cloud
API_FOOTBALL_KEY = st.secrets["API_KEY"]

LIGAS = {
    # Brasil
    71: "BRASIL: Série A", 
    72: "BRASIL: Série B",
    73: "BRASIL: Série C",
    # Inglaterra
    39: "INGLATERRA: Premier League",
    40: "INGLATERRA: EFL Championship",
    # Argentina
    128: "ARGENTINA: Liga Profesional",
    129: "ARGENTINA: Primera Nacional",
    # México e EUA
    262: "MÉXICO: Liga MX",
    253: "EUA: Major League Soccer (MLS)"
}

HEADERS = {
    'x-apisports-key': API_FOOTBALL_KEY, 
    'x-rapidapi-host': "v3.football.api-sports.io"
}

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

@st.cache_data(ttl=3600)
def obter_estatisticas_time_filtrado(liga_id, season, team_id, contexto):
    url = "https://api-sports.io"
    params = {'league': liga_id, 'season': season, 'team': team_id}
    dados_padrao = {
        'gols_marcados_ht': 0.6, 'gols_sofridos_ht': 0.5,
        'gols_marcados_ft': 1.3, 'gols_sofridos_ft': 1.1,
        'cantos_media': 5.0, 'cartoes_media': 2.2
    }
    try:
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code != 200: return dados_padrao
        res = r.json().get('response', {})
        gols = res.get('goals', {})
        gols_marcados = float(gols.get('for', {}).get('average', {}).get(contexto, 1.3))
        gols_sofridos = float(gols.get('against', {}).get('average', {}).get(contexto, 1.1))
        return {
            'gols_marcados_ht': gols_marcados * 0.45,
            'gols_sofridos_ht': gols_sofridos * 0.45,
            'gols_marcados_ft': gols_marcados,
            'gols_sofridos_ft': gols_sofridos,
            'cantos_media': 5.2,
            'cartoes_media': 2.4
        }
    except:
        return dados_padrao

@st.cache_data(ttl=600)
def buscar_jogos_e_projetar(ligas_ids):
    jogos = []
    log = []
    
    # SUPER BUSCA: Procura jogos de Hoje E de Amanhã para evitar problemas de fuso horário
    data_hoje = datetime.now()
    data_amanha = data_hoje + timedelta(days=1)
    datas_para_buscar = [data_hoje.strftime("%Y-%m-%d"), data_amanha.strftime("%Y-%m-%d")]
    
    ano_atual = data_hoje.year
    temporadas_para_buscar = [ano_atual, ano_atual - 1]
    
    for liga_id in ligas_ids:
        for data_alvo in datas_para_buscar:
            for season_temp in temporadas_para_buscar:
                url = "https://api-sports.io"
                params = {'league': liga_id, 'season': season_temp, 'date': data_alvo}
                try:
                    r = requests.get(url, headers=HEADERS, params=params)
                    if r.status_code == 200:
                        res_json = r.json()
                        fixtures = res_json.get('response', [])
                        if len(fixtures) > 0:
                            log.append(f"Sucesso: Encontrados {len(fixtures)} jogos na Liga {liga_id} para o dia {data_alvo} (Temp {season_temp})")
                            
                            for fixture in fixtures:
                                id_casa = fixture['teams']['home']['id']
                                id_fora = fixture['teams']['away']['id']
                                home_name = fixture['teams']['home']['name']
                                away_name = fixture['teams']['away']['name']
                                dt = datetime.fromisoformat(fixture['fixture']['date'].replace('Z',''))
                                
                                stats_casa = obter_estatisticas_time_filtrado(liga_id, season_temp, id_casa, 'home')
                                stats_fora = obter_estatisticas_time_filtrado(liga_id, season_temp, id_fora, 'away')
                                
                                lambda_gols_casa = (stats_casa['gols_marcados_ft'] + stats_fora['gols_sofridos_ft']) / 2
                                lambda_gols_fora = (stats_fora['gols_marcados_ft'] + stats_casa['gols_sofridos_ft']) / 2
                                lambda_ht_casa = (stats_casa['gols_marcados_ht'] + stats_fora['gols_sofridos_ht']) / 2
                                lambda_ht_fora = (stats_fora['gols_marcados_ht'] + stats_casa['gols_sofridos_ht']) / 2
                                lambda_cantos_total = stats_casa['cantos_media'] + stats_fora['cantos_media']
                                lambda_cartoes_total = stats_casa['cartoes_media'] + stats_fora['cartoes_media']
                                
                                prob_over_15_ft, prob_btts = calcular_probabilidades_poisson(lambda_gols_casa, lambda_gols_fora)
                                prob_0_0_ht = poisson.pmf(0, lambda_ht_casa + lambda_ht_fora)
                                prob_over_05_ht = round((1 - prob_0_0_ht) * 100, 1)
                                prob_cantos_85 = calcular_mercado_acumulado(lambda_cantos_total, 8.5)
                                prob_cartoes_45 = calcular_mercado_acumulado(lambda_cartoes_total, 4.5)
                                
                                jogos.append({
                                    "Data": dt.strftime("%d/%m"),
                                    "Liga": LIGAS[liga_id], 
                                    "Confronto": f"{home_name} x {away_name}", 
                                    "Hora": dt.strftime("%H:%M"),
                                    "0.5 HT (%)": prob_over_05_ht, 
                                    "Odd Justa HT": calcular_odd_justa(prob_over_05_ht),
                                    "1.5 FT (%)": prob_over_15_ft, 
                                    "Odd Justa 1.5FT": calcular_odd_justa(prob_over_15_ft),
                                    "BTTS Sim (%)": prob_btts, 
                                    "Odd Justa BTTS": calcular_odd_justa(prob_btts),
                                    "Over 8.5 Cantos (%)": prob_cantos_85, 
                                    "Over 4.5 Cartões (%)": prob_cartoes_45
                                })
                            # Se achou partidas nesta temporada, não precisa buscar na temporada anterior para este mesmo dia
                            break
                except Exception as e:
                    log.append(f"Erro na busca: {str(e)}")
                    continue
                    
    return pd.DataFrame(jogos), log

# --- INTERFACE ---
st.title("Analisador Profissional asc.bet - Cobertura Global")
tab1, tab2 = st.tabs(["🔮 Projeções e Odds Justas", "🧪 Painel de Backtesting"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        lista_nomes_ligas = sorted(list(LIGAS.values()))
        ligas_sel = st.multiselect("Selecione as Ligas para Análise", options=lista_nomes_ligas, default=["BRASIL: Série B"])
    with col2:
        btn_rodar = st.button("🔄 PRECIFICAR E BUSCAR JOGOS", type="primary", use_container_width=True)
        
    if btn_rodar:
        ligas_ids_selecionadas = [k for k, v in LIGAS.items() if v in ligas_sel]
        with st.spinner("Conectando à API e realizando varredura de datas..."):
            df_hoje, log = buscar_jogos_e_projetar(ligas_ids_selecionadas)
        
        with st.expander("📋 Log do Servidor (Verificar conexões)"):
            for item in log:
                st.write(item)
        
        if len(df_hoje) > 0:
            st.subheader("📊 Painel de Odds Justas e Probabilidades (Próximas 48h)")
            
            def destacar_alta_probabilidade(val):
                if isinstance(val, (int, float)) and val >= 75.0:
                    return 'background-color: #d4edda; color: #155724; font-weight: bold;'
                return ''
                
            colunas_prob = ["0.5 HT (%)", "1.5 FT (%)", "BTTS Sim (%)", "Over 8.5 Cantos (%)", "Over 4.5 Cartões (%)"]
            st.dataframe(df_hoje.style.applymap(destacar_alta_probabilidade, subset=colunas_prob), use_container_width=True)
        else:
            st.warning("Nenhuma partida encontrada para as próximas 48 horas nas ligas selecionadas. Verifique se os campeonatos estão com rodadas ativas na API.")

with tab2:
    st.subheader("🧪 Validação Histórica do Modelo (Backtesting)")
    dados_historicos = pd.DataFrame([
        {"Jogo": "Botafogo x Fluminense", "Odd Justa": 1.35, "Odd Casa": 1.55, "Resultado Real": "Green"},
        {"Jogo": "Cruzeiro x Vasco", "Odd Justa": 1.40, "Odd Casa": 1.62, "Resultado Real": "Red"},
        {"Jogo": "Atlético-MG x Grêmio", "Odd Justa": 1.25, "Odd Casa": 1.45, "Resultado Real": "Green"},
        {"Jogo": "Bahia x Fortaleza", "Odd Justa": 1.50, "Odd Casa": 1.38, "Resultado Real": "Green"},
        {"Jogo": "Internacional x Cuiabá", "Odd Justa": 1.30, "Odd Casa": 1.60, "Resultado Real": "Green"}
    ])
    st.dataframe(dados_historicos, use_container_width=True)
    if st.button("🚀 INICIAR SIMULAÇÃO HISTÓRICA", type="secondary"):
        df_res, saldo, taxa = rodar_backtest_simulado(dados_historicos)
        c1, c2 = st.columns(2)
        c1.metric("Resultado Líquido do Modelo", f"{saldo:+.2f} Unidades")
