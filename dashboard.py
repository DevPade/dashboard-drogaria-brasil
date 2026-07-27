import streamlit as st
import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from sqlalchemy import create_engine

import os

# Carrega variáveis do arquivo .env
load_dotenv()

# Conexão Snowflake usando variáveis de ambiente
conn = snowflake.connector.connect(
    user=os.getenv('SNOWFLAKE_USER'),
    password=os.getenv('SNOWFLAKE_PASSWORD'),
    account=os.getenv('SNOWFLAKE_ACCOUNT'),
    warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
    role=os.getenv('SNOWFLAKE_ROLE'),
    database=os.getenv('SNOWFLAKE_DATABASE'),
    schema=os.getenv('SNOWFLAKE_SCHEMA'),
)


engine = create_engine('snowflake://', creator=lambda: conn)

st.set_page_config(page_title="O que Comprar - DROGARIA BRASIL", layout="wide")

st.title("O que Comprar para Melhorar as Vendas")
st.markdown("**DROGARIA BRASIL** | Maio 2026 | Comparação por varejos")

SUA_FARMACIA = "DROGARIA BRASIL"

@st.cache_data
def carregar_dados():
    
    # 1. Resumo por varejo
    query_resumo = """
        SELECT
            "UTC_DESC_VAREJO" AS varejo,
            SUM("VAL_R$") AS faturamento
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "PER_MES" = '202605'
            AND "INF_DESC" != 'DROGARIA BRASIL'
        GROUP BY "UTC_DESC_VAREJO"
        ORDER BY faturamento DESC
    """
    
    # 2. Seu faturamento
    query_seu = """
        SELECT SUM("VAL_R$") AS faturamento
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "PER_MES" = '202605'
            AND "INF_DESC" = 'DROGARIA BRASIL'
    """
    
    # 3. Produtos que outros vendem e você não
    query_oportunidades = """
        SELECT 
            "APRES_DESC" AS produto,
            "APRES_MARCA" AS marca,
            "APRES_SECAO_LOJA" AS secao,
            SUM("VAL_R$") AS faturamento,
            SUM("VAL_UND") AS unidades,
            COUNT(DISTINCT "UTC_DESC_VAREJO") AS varejos
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "PER_MES" = '202605'
            AND "INF_DESC" != 'DROGARIA BRASIL'
            AND "APRES_EAN" NOT IN (
                SELECT DISTINCT "APRES_EAN"
                FROM REPORT_INFORMANTE_E_MERCADO
                WHERE "PER_MES" = '202605'
                    AND "INF_DESC" = 'DROGARIA BRASIL'
            )
        GROUP BY "APRES_DESC", "APRES_MARCA", "APRES_SECAO_LOJA"
        ORDER BY faturamento DESC
    """
    
    # 4. Suas seções
    query_suas_secoes = """
        SELECT
            "APRES_SECAO_LOJA" AS secao,
            SUM("VAL_R$") AS faturamento
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "PER_MES" = '202605'
            AND "INF_DESC" = 'DROGARIA BRASIL'
            AND "APRES_SECAO_LOJA" IS NOT NULL
        GROUP BY "APRES_SECAO_LOJA"
    """
    
    # 5. Seções outros
    query_outras_secoes = """
        SELECT
            "APRES_SECAO_LOJA" AS secao,
            SUM("VAL_R$") AS faturamento
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "PER_MES" = '202605'
            AND "INF_DESC" != 'DROGARIA BRASIL'
            AND "APRES_SECAO_LOJA" IS NOT NULL
        GROUP BY "APRES_SECAO_LOJA"
    """
    
    # 6. Lista de varejos
    query_varejos = """
        SELECT DISTINCT "UTC_DESC_VAREJO" AS varejo
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "PER_MES" = '202605'
            AND "INF_DESC" != 'DROGARIA BRASIL'
        ORDER BY varejo
    """
    
    df_resumo = pd.read_sql(query_resumo, engine)
    df_seu = pd.read_sql(query_seu, engine)
    df_oportunidades = pd.read_sql(query_oportunidades, engine)
    df_suas_secoes = pd.read_sql(query_suas_secoes, engine)
    df_outras_secoes = pd.read_sql(query_outras_secoes, engine)
    df_varejos = pd.read_sql(query_varejos, engine)
    
    return df_resumo, df_seu, df_oportunidades, df_suas_secoes, df_outras_secoes, df_varejos

df_resumo, df_seu, df_oportunidades, df_suas_secoes, df_outras_secoes, df_varejos = carregar_dados()

# Formatação
def R1(valor):
    try:
        if pd.isna(valor) or valor is None:
            return "R$ 0,00"
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def N(valor):
    try:
        if pd.isna(valor) or valor is None:
            return "0"
        return f"{int(valor):,}".replace(",", ".")
    except:
        return "0"


def calcular_potencial_realista(df_oportunidades, seu_faturamento):
    """
    Calcula potencial de compra realista considerando:
    - Penetração de mercado (70%)
    - Capacidade financeira (20% do faturamento)
    - Foco nos melhores produtos (Top 50)
    """
    if df_oportunidades.empty:
        return 0, 0, 0, 0
    
    # 1. Potencial bruto (como está hoje)
    potencial_bruto = df_oportunidades['faturamento'].sum()
    
    # 2. Ajuste por penetração de mercado (70%)
    potencial_penetracao = potencial_bruto * 0.70
    
    # 3. Limite por capacidade financeira (20% do seu faturamento)
    capacidade_max = seu_faturamento * 0.20
    
    # 4. Seleciona produtos mais relevantes (Top 50 por faturamento)
    df_top = df_oportunidades.nlargest(50, 'faturamento')
    potencial_top50 = df_top['faturamento'].sum() * 0.70
    
    # 5. Potencial final = mínimo entre os ajustes
    potencial_final = min(potencial_top50, capacidade_max)
    
    # 6. Quantos produtos cabem no orçamento
    df_ordenado = df_oportunidades.sort_values('faturamento', ascending=False)
    df_cabivel = df_ordenado[df_ordenado['faturamento'].cumsum() <= capacidade_max]
    produtos_cabiveis = len(df_cabivel)
    
    return potencial_bruto, potencial_penetracao, potencial_final, produtos_cabiveis

# ========== SIDEBAR ==========
st.sidebar.title("⚙️ Filtros")

varejos_lista = ['TODOS'] + df_varejos['varejo'].tolist()
varejo_selecionado = st.sidebar.selectbox("Comparar com:", varejos_lista)

# ========== CARDS ==========
st.markdown("---")
col1, col2, col3 = st.columns(3)

seu_fat = df_seu['faturamento'].iloc[0] if not df_seu.empty and not pd.isna(df_seu['faturamento'].iloc[0]) else 0

if varejo_selecionado != 'TODOS':
    media_outros = df_resumo[df_resumo['varejo'] == varejo_selecionado]['faturamento'].iloc[0] if not df_resumo[df_resumo['varejo'] == varejo_selecionado].empty else 0
else:
    media_outros = df_resumo['faturamento'].mean() if not df_resumo.empty else 0

potencial_bruto, potencial_penetracao, potencial_final, produtos_cabiveis = calcular_potencial_realista(df_oportunidades, seu_fat)
potencial = potencial_final

with col1:
    st.metric("Seu Faturamento", R1(seu_fat))

with col2:
    label = f" {varejo_selecionado}" if varejo_selecionado != 'TODOS' else "Média dos Varejos"
    st.metric(label, R1(media_outros),
             delta=R1(seu_fat - media_outros) if seu_fat and media_outros else None)

with col3:
   with col3:
    st.metric(
        "Potencial de Compra", 
        R1(potencial),
        delta=f"{((potencial/seu_fat)*100):.1f}% do faturamento" if seu_fat > 0 else None,
        help=f"""
        Potencial realista considerando:
        • 70% de penetração de mercado
        • Limite de 20% do faturamento (R$ {seu_fat * 0.20:,.2f})
        • Top 50 produtos mais relevantes
        • {produtos_cabiveis} produtos cabem no orçamento
        """
    )

# ========== TABS ==========
tab1, tab2, tab3 = st.tabs(["🛍️ O QUE COMPRAR", "📊 POR SEÇÃO", "🏪 POR VAREJO"])

with tab1:
    st.subheader("Produtos que Outros Varejos Vendem e a Drogaria Brasil Não")
    
    if df_oportunidades.empty:
        st.warning("Nenhum produto encontrado.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            secoes = ['TODAS'] + sorted(df_oportunidades['secao'].dropna().unique().tolist())
            secao_filtro = st.selectbox("Seção", secoes, key='secao_op')
        with col2:
            marcas = ['TODAS'] + sorted(df_oportunidades['marca'].dropna().unique().tolist())
            marca_filtro = st.selectbox("Marca", marcas, key='marca_op')
        
        df = df_oportunidades.copy()
        if secao_filtro != 'TODAS':
            df = df[df['secao'] == secao_filtro]
        if marca_filtro != 'TODAS':
            df = df[df['marca'] == marca_filtro]
        
        df_show = df.copy()
        df_show['Faturamento'] = df_show['faturamento'].apply(R1)
        df_show['Unidades'] = df_show['unidades'].apply(N)
        df_show['Varejos'] = df_show['varejos'].apply(N)
        
        st.dataframe(
            df_show[['produto', 'marca', 'secao', 'Faturamento', 'Unidades', 'Varejos']],
            use_container_width=True,
            hide_index=True,
            height=500
        )
        
        st.metric("Total de Oportunidades", N(len(df)))
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Lista", csv, "produtos_para_comprar.csv")

with tab2:
    st.subheader("Comparativo por Seção")
    
    if df_suas_secoes.empty and df_outras_secoes.empty:
        st.warning("Nenhum dado de seção encontrado.")
    else:
        df_secoes = df_suas_secoes.merge(
            df_outras_secoes,
            on='secao',
            how='outer',
            suffixes=('_drogaria', '_outros')
        ).fillna(0)
        
        df_secoes['Oportunidade'] = df_secoes['faturamento_outros'] - df_secoes['faturamento_drogaria']
        df_secoes = df_secoes.sort_values('Oportunidade', ascending=False)
        
        df_show_secoes = df_secoes.copy()
        df_show_secoes['Seu Faturamento'] = df_show_secoes['faturamento_drogaria'].apply(R1)
        df_show_secoes['Faturamento Outros'] = df_show_secoes['faturamento_outros'].apply(R1)
        df_show_secoes['Oportunidade'] = df_show_secoes['Oportunidade'].apply(R1)
        
        st.dataframe(
            df_show_secoes[['secao', 'Seu Faturamento', 'Faturamento Outros', 'Oportunidade']],
            use_container_width=True,
            hide_index=True,
            height=500
        )

with tab3:
    st.subheader("Comparativo por Varejo")
    
    if df_resumo.empty:
        st.warning("Nenhum dado de varejo encontrado.")
    else:
        df_show_varejos = df_resumo.copy()
        df_show_varejos['Faturamento'] = df_show_varejos['faturamento'].apply(R1)
        df_show_varejos['Diferença'] = df_show_varejos['faturamento'].apply(
            lambda x: R1(seu_fat - x) if seu_fat else R1(0)
        )
        
        st.dataframe(
            df_show_varejos[['varejo', 'Faturamento', 'Diferença']],
            use_container_width=True,
            hide_index=True,
            height=500
        )
        
        acima = len(df_resumo[df_resumo['faturamento'] > seu_fat])
        abaixo = len(df_resumo[df_resumo['faturamento'] < seu_fat])
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Varejos com faturamento MAIOR que o seu", N(acima))
        with col2:
            st.metric("Varejos com faturamento MENOR que o seu", N(abaixo))

conn.close()