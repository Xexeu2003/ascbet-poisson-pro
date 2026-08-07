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

# O sistema continuará puxando de forma invisível a chave que você salvou nos Secrets
API_FOOTBALL_KEY = st.secrets["API_KEY"]

# DICIONÁRIO EXPANDIDO COM AS IDs OFICIAIS DE TODAS AS LIGAS PEDIDAS (API-FOOTBALL)
LIGAS = {
    # Brasil
    71: "BRASIL: Série A", 
    72: "BRASIL: Série B",
    73: "BRASIL: Série C",
    # Inglaterra
    39: "INGLATERRA: Premier League",
    40: "INGLATERRA: EFL Championship",
    41: "INGLATERRA: EFL League One",
    42: "INGLATERRA: EFL League Two",
    # Argentina
    128: "ARGENTINA: Liga Profesional",
    129: "ARGENTINA: Primera Nacional",
    # Colômbia
    239: "COLÔMBIA: Liga BetPlay Dimayor",
    240: "COLÔMBIA: Torneo BetPlay Dimayor",
    # Chile
    265: "CHILE: Primera División",
    266: "CHILE: Primera B",
    # Uruguai
    268: "URUGUAI: Primera División",
    269: "URUGUAI: Segunda División",
    # Paraguai
    252: "PARAGUAI: División de Honor",
    258: "PARAGUAI: División Intermedia",
    # Venezuela
    272: "VENEZUELA: Liga FUTVE",
    273: "VENEZUELA: Liga FUTVE 2",
    # México e EUA
    262: "MÉXICO: Liga MX",
    253: "EUA: Major League Soccer (MLS)",
    254: "EUA: USL Championship",
    # Holanda e Bélgica
    88: "HOLANDA: Eredivisie",
    89: "HOLANDA: Eerste Divisie",
    144: "BÉLGICA: Jupiler Pro League",
    145: "BÉLGICA: Challenger Pro League",
    # Escandinávia (Suécia, Dinamarca, Finlândia, Islândia)
    113: "SUÉCIA: Allsvenskan",
    114: "SUÉCIA: Superettan",
    119: "DINAMARCA: Superligaen",
    120: "DINAMARCA: 1. Division",
    244: "FINLÂNDIA: Veikkausliiga",
    172: "ISLÂNDIA: Besta deild karla",
    # Polônia e Croácia
    106: "POLÔNIA: Ekstraklasa",
    107: "POLÔNIA: I Liga",
    210: "CROÁCIA: HNL",
    # Ásia e Oceania
    188: "AUSTRÁLIA: A-League",
    98: "JAPÃO: J1 League",
    99: "JAPÃO: J2 League",
    169: "CHINA: Super League (CSL)",
    292: "COREIA DO SUL: K League 1",
    293: "COREIA DO SUL: K League 2",
    # Europa Central e Leste (Suíça, Turquia, Grécia, Israel, Hungria)
    207: "SUÍÇA: Super League",
    203: "TURQUIA: Süper Lig",
    204: "TURQUIA: TFF 1. Lig",
    197: "GRÉCIA: Super League 1",
    383: "ISRAEL: Ligat Ha'Al",
    271: "HUNGRIA: NB I",
    # Alemanha
    78: "ALEMANHA: Bundesliga",
    79: "ALEMANHA: 2. Bundesliga",
    80: "ALEMANHA: 3. Liga",
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
    # Índia e Arábia Saudita
    323: "ÍNDIA: Indian Super League",
    307: "ARÁBIA SAUDITA: Saudi Pro League"
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
        
    t = Table(dados, colWidths=[120, 140, 50, 70, 70, 70])
    t.setStyle(TableStyle([
