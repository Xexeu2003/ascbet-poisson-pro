import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from scipy.stats import poisson
from io import BytesIO

# Importações do ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="Analisador Premium asc.bet", layout="wide")

# Insira sua chave obtida em api-football.com
API_FOOTBALL_KEY = "API_FOOTBALL_KEY = st.secrets"


LIGAS = {
    71: "BRASILEIRÃO SÉRIE A", 
    72: "BRASILEIRÃO SÉRIE B", 
    39: "PREMIER LEAGUE"
}

HEADERS = {
    'x-apisports-key': API_FOOTBALL_KEY, 
    'x-rapidapi-host': "v3.football.api-sports.io"
}

# --- MATEMÁTICA E PRECIFICAÇÃO ---
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

@st.cache_data(ttl=1800)
def buscar_jogos_e_projetar(ligas_ids):
    jogos = []
    log = []
    hoje = datetime.now().strftime("%Y-%m-%d")
    ano_atual = datetime.now().year
    
    for liga_id in ligas_ids:
        url = "https://api-sports.io"
        params = {'league': liga_id, 'season': ano_atual, 'date': hoje}
        try:
            r = requests.get(url, headers=HEADERS, params=params)
            log.append(f"Liga {liga_id} - Status: {r.status_code}")
            if r.status_code != 200: continue
            data = r.json()
        except Exception as e:
            log.append(f"Erro na liga {liga_id}: {str(e)}")
            continue
        
        for fixture in data.get('response', []):
            id_casa = fixture['teams']['home']['id']
            id_fora = fixture['teams']['away']['id']
            home_name = fixture['teams']['home']['name']
            away_name = fixture['teams']['away']['name']
            dt = datetime.fromisoformat(fixture['fixture']['date'].replace('Z',''))
            
            stats_casa = obter_estatisticas_time_filtrado(liga_id, ano_atual, id_casa, 'home')
            stats_fora = obter_estatisticas_time_filtrado(liga_id, ano_atual, id_fora, 'away')
            
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
                "Liga": LIGAS[liga_id], "Confronto": f"{home_name} x {away_name}", "Hora": dt.strftime("%H:%M"),
                "0.5 HT (%)": prob_over_05_ht, "Odd Justa HT": calcular_odd_justa(prob_over_05_ht),
                "1.5 FT (%)": prob_over_15_ft, "Odd Justa 1.5FT": calcular_odd_justa(prob_over_15_ft),
                "BTTS Sim (%)": prob_btts, "Odd Justa BTTS": calcular_odd_justa(prob_btts),
                "Over 8.5 Cantos (%)": prob_cantos_85, "Over 4.5 Cartões (%)": prob_cartoes_45
            })
    return pd.DataFrame(jogos), log

# --- ENGINE DE BACKTESTING ---
def rodar_backtest_simulado(df_historico_jogos):
    saldo_unidades = 0.0
    apostas_feitas = 0
    acertos = 0
    resultados_backtest = []
    
    for jogo in df_historico_jogos.to_dict(orient='records'):
        if jogo['Odd Casa'] > jogo['Odd Justa']:
            apostas_feitas += 1
            if jogo['Resultado Real'] == "Green":
                saldo_unidades += (jogo['Odd Casa'] - 1)
                acertos += 1
                status = "✅ GANHOU"
            else:
                saldo_unidades -= 1
                status = "❌ PERDEU"
            resultados_backtest.append({
                "Jogo": jogo['Jogo'], "Odd Casa": jogo['Odd Casa'], 
                "Odd Justa": jogo['Odd Justa'], "Status": status, "Saldo Acumulado": round(saldo_unidades, 2)
            })
    tx_acerto = (acertos / apostas_feitas * 100) if apostas_feitas > 0 else 0
    return pd.DataFrame(resultados_backtest), saldo_unidades, tx_acerto

# --- RELATÓRIO PDF ---
def gerar_pdf_com_odds(df):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    
    style_tit = ParagraphStyle('T', fontSize=18, leading=22, textColor=colors.HexColor('#1A365D'), alignment=1, spaceAfter=15)
    story.append(Paragraph("<b>asc.bet Pro</b> - Relatório de Odds Justas", style_tit))
    
    headers = ["Liga", "Confronto", "Hora", "0.5HT Justa", "1.5FT Justa", "BTTS Justa"]
    dados = [headers]
    for r in df.to_dict(orient='records'):
        dados.append([r['Liga'], r['Confronto'], r['Hora'], f"@{r['Odd Justa HT']}", f"@{r['Odd Justa 1.5FT']}", f"@{r['Odd Justa BTTS']}"])
        
    t = Table(dados, colWidths=[90, 160, 45, 70, 70, 70])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('FONTSIZE', (0,0), (-1,-1), 9)
    ]))
    story.append(t)
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- INTERFACE STREAMLIT ---
st.title("Analisador Profissional asc.bet - Sistema Online")
tab1, tab2 = st.tabs(["🔮 Projeções e Odds Justas", "🧪 Painel de Backtesting"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        ligas_sel = st.multiselect("Selecione as Ligas", options=list(LIGAS.values()), default=["BRASILEIRÃO SÉRIE A"])
    with col2:
        btn_rodar = st.button("🔄 PRECIFICAR E BUSCAR JOGOS DE HOJE", type="primary", use_container_width=True)
        
    if btn_rodar:
        if API_FOOTBALL_KEY == "COLA_SUA_CHAVE_AQUI":
            st.error("Insira sua chave API no código fonte (variável API_FOOTBALL_KEY).")
        else:
            with st.spinner("Puxando estatísticas e aplicando Poisson..."):
                df_hoje, log = buscar_jogos_e_projetar(ligas_ids_sel = [k for k,v in LIGAS.items() if v in ligas_sel])
            
            if len(df_hoje) > 0:
                st.subheader("📊 Painel de Odds Justas e Probabilidades")
                st.dataframe(df_hoje, use_container_width=True)
                
                pdf = gerar_pdf_com_odds(df_hoje)
                st.download_button("📥 DOWNLOAD RELATÓRIO ODDS JUSTAS (PDF)", data=pdf, file_name="odds_justas.pdf", mime="application/pdf")
            else:
                st.warning("Nenhum jogo programado para hoje nestas ligas.")

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
