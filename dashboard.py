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
st.markdown("**DROGARIA BRASIL** | Comparação por varejos")

SUA_FARMACIA = "DROGARIA BRASIL"

@st.cache_data(ttl=3600)
def carregar_periodos():
    """Carrega lista de períodos disponíveis"""
    query_periodos = """
        SELECT DISTINCT "PER_MES" AS periodo
        FROM REPORT_INFORMANTE_E_MERCADO
        ORDER BY periodo ASC
    """
    df_periodos = pd.read_sql(query_periodos, engine)
    return df_periodos

@st.cache_data(ttl=3600)
def carregar_dados(periodo_inicio, periodo_fim):
    """Carrega todos os dados com filtro de período (de/até)"""
    
    # Define filtro de período
    if periodo_inicio == 'TODOS' or periodo_fim == 'TODOS':
        filtro_periodo = ""
    else:
        filtro_periodo = f"AND \"PER_MES\" BETWEEN '{periodo_inicio}' AND '{periodo_fim}'"
    
    # 1. Resumo por varejo
    query_resumo = f"""
        SELECT
            "UTC_DESC_VAREJO" AS varejo,
            SUM("VAL_R$") AS faturamento,
            COUNT(DISTINCT "APRES_EAN") AS produtos,
            SUM("VAL_UND") AS unidades
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "INF_DESC" != '{SUA_FARMACIA}'
            {filtro_periodo}
        GROUP BY "UTC_DESC_VAREJO"
        ORDER BY faturamento DESC
    """
    
    # 2. Seu faturamento
    query_seu = f"""
        SELECT 
            SUM("VAL_R$") AS faturamento,
            COUNT(DISTINCT "APRES_EAN") AS produtos,
            SUM("VAL_UND") AS unidades
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "INF_DESC" = '{SUA_FARMACIA}'
            {filtro_periodo}
    """
    
    # 3. Produtos que outros vendem e você não
    query_oportunidades = f"""
        SELECT 
            "APRES_DESC" AS produto,
            "APRES_MARCA" AS marca,
            "APRES_SECAO_LOJA" AS secao,
            "APRES_EAN" AS ean,
            SUM("VAL_R$") AS faturamento,
            SUM("VAL_UND") AS unidades,
            ROUND(SUM("VAL_R$") / NULLIF(SUM("VAL_UND"), 0), 2) AS preco_medio,
            COUNT(DISTINCT "UTC_DESC_VAREJO") AS varejos
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "INF_DESC" != '{SUA_FARMACIA}'
            {filtro_periodo}
            AND "APRES_EAN" NOT IN (
                SELECT DISTINCT "APRES_EAN"
                FROM REPORT_INFORMANTE_E_MERCADO
                WHERE "INF_DESC" = '{SUA_FARMACIA}'
                    {filtro_periodo}
            )
        GROUP BY "APRES_DESC", "APRES_MARCA", "APRES_SECAO_LOJA", "APRES_EAN"
        ORDER BY faturamento DESC
    """
    
    # 4. Suas seções
    query_suas_secoes = f"""
        SELECT
            "APRES_SECAO_LOJA" AS secao,
            SUM("VAL_R$") AS faturamento,
            COUNT(DISTINCT "APRES_EAN") AS produtos,
            SUM("VAL_UND") AS unidades
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "INF_DESC" = '{SUA_FARMACIA}'
            AND "APRES_SECAO_LOJA" IS NOT NULL
            {filtro_periodo}
        GROUP BY "APRES_SECAO_LOJA"
    """
    
    # 5. Seções outros
    query_outras_secoes = f"""
        SELECT
            "APRES_SECAO_LOJA" AS secao,
            SUM("VAL_R$") AS faturamento,
            COUNT(DISTINCT "APRES_EAN") AS produtos,
            SUM("VAL_UND") AS unidades
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "INF_DESC" != '{SUA_FARMACIA}'
            AND "APRES_SECAO_LOJA" IS NOT NULL
            {filtro_periodo}
        GROUP BY "APRES_SECAO_LOJA"
    """
    
    # 6. Lista de varejos
    query_varejos = f"""
        SELECT DISTINCT "UTC_DESC_VAREJO" AS varejo
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "INF_DESC" != '{SUA_FARMACIA}'
            {filtro_periodo}
        ORDER BY varejo
    """
    
    # 7. Top 10 produtos da Drogaria Brasil
    query_top_produtos = f"""
        SELECT 
            "APRES_DESC" AS produto,
            SUM("VAL_R$") AS faturamento,
            SUM("VAL_UND") AS unidades,
            ROUND(SUM("VAL_R$") / NULLIF(SUM("VAL_UND"), 0), 2) AS preco_medio
        FROM REPORT_INFORMANTE_E_MERCADO
        WHERE "INF_DESC" = '{SUA_FARMACIA}'
            {filtro_periodo}
        GROUP BY "APRES_DESC"
        ORDER BY faturamento DESC
        LIMIT 10
    """
    
    df_resumo = pd.read_sql(query_resumo, engine)
    df_seu = pd.read_sql(query_seu, engine)
    df_oportunidades = pd.read_sql(query_oportunidades, engine)
    df_suas_secoes = pd.read_sql(query_suas_secoes, engine)
    df_outras_secoes = pd.read_sql(query_outras_secoes, engine)
    df_varejos = pd.read_sql(query_varejos, engine)
    df_top_produtos = pd.read_sql(query_top_produtos, engine)
    
    return df_resumo, df_seu, df_oportunidades, df_suas_secoes, df_outras_secoes, df_varejos, df_top_produtos

# Carregar períodos disponíveis
df_periodos = carregar_periodos()

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

def formatar_periodo(periodo):
    """Formata 202605 para Mai/2026"""
    if periodo == 'TODOS':
        return 'Todos'
    ano = periodo[:4]
    mes = periodo[4:]
    meses = {
        '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
        '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
        '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez'
    }
    return f"{meses.get(mes, mes)}/{ano}"

def calcular_potencial_realista(df_oportunidades, seu_faturamento):
    """Calcula potencial de compra realista"""
    if df_oportunidades.empty or seu_faturamento == 0:
        return 0, 0, 0, 0
    
    potencial_bruto = df_oportunidades['faturamento'].sum()
    potencial_penetracao = potencial_bruto * 0.70
    capacidade_max = seu_faturamento * 0.20
    
    df_top = df_oportunidades.nlargest(50, 'faturamento')
    potencial_top50 = df_top['faturamento'].sum() * 0.70
    
    potencial_final = min(potencial_top50, capacidade_max)
    
    df_ordenado = df_oportunidades.sort_values('faturamento', ascending=False)
    df_cabivel = df_ordenado[df_ordenado['faturamento'].cumsum() <= capacidade_max]
    produtos_cabiveis = len(df_cabivel)
    
    return potencial_bruto, potencial_penetracao, potencial_final, produtos_cabiveis

# ========== SIDEBAR ==========
st.sidebar.title("⚙️ Filtros")

# Filtro de período DE/ATÉ
st.sidebar.subheader("📅 Período")

col_de, col_ate = st.sidebar.columns(2)

with col_de:
    periodo_de = st.selectbox(
        "De:",
        ['TODOS'] + df_periodos['periodo'].tolist(),
        format_func=formatar_periodo,
        key='periodo_de'
    )

with col_ate:
    # Se selecionou TODOS no "De", desabilita o "Até"
    if periodo_de == 'TODOS':
        periodo_ate = st.selectbox(
            "Até:",
            ['TODOS'],
            disabled=True,
            key='periodo_ate_disabled'
        )
    else:
        # Filtra períodos a partir do "De"
        periodos_ate = df_periodos[df_periodos['periodo'] >= periodo_de]['periodo'].tolist()
        periodo_ate = st.selectbox(
            "Até:",
            periodos_ate,
            format_func=formatar_periodo,
            key='periodo_ate'
        )

# Carregar dados com o período selecionado
if periodo_de == 'TODOS':
    df_resumo, df_seu, df_oportunidades, df_suas_secoes, df_outras_secoes, df_varejos, df_top_produtos = carregar_dados('TODOS', 'TODOS')
else:
    df_resumo, df_seu, df_oportunidades, df_suas_secoes, df_outras_secoes, df_varejos, df_top_produtos = carregar_dados(periodo_de, periodo_ate)

# Mostrar período selecionado
if periodo_de == 'TODOS':
    st.sidebar.caption("📅 Todos os períodos")
else:
    st.sidebar.caption(f"📅 {formatar_periodo(periodo_de)} até {formatar_periodo(periodo_ate)}")

st.sidebar.markdown("---")

# Filtro de varejo
varejos_lista = ['Todos'] + df_varejos['varejo'].tolist()
varejo_selecionado = st.sidebar.selectbox(
    "🏪 Comparar com:",
    varejos_lista,
    help="Selecione um varejo específico ou Todos para média"
)

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Seus Números")
seu_fat = df_seu['faturamento'].iloc[0] if not df_seu.empty and not pd.isna(df_seu['faturamento'].iloc[0]) else 0
seus_produtos = df_seu['produtos'].iloc[0] if not df_seu.empty else 0
suas_unidades = df_seu['unidades'].iloc[0] if not df_seu.empty else 0

st.sidebar.metric("Faturamento", R1(seu_fat))
st.sidebar.metric("Produtos", N(seus_produtos))
st.sidebar.metric("Unidades", N(suas_unidades))

# ========== CARDS PRINCIPAIS ==========
col1, col2, col3 = st.columns(3)

if varejo_selecionado != 'Todos':
    media_outros = df_resumo[df_resumo['varejo'] == varejo_selecionado]['faturamento'].iloc[0] if not df_resumo[df_resumo['varejo'] == varejo_selecionado].empty else 0
else:
    media_outros = df_resumo['faturamento'].mean() if not df_resumo.empty else 0

potencial_bruto, potencial_penetracao, potencial_final, produtos_cabiveis = calcular_potencial_realista(df_oportunidades, seu_fat)

with col1:
    st.metric("Seu Faturamento", R1(seu_fat))

with col2:
    label = f"{varejo_selecionado}" if varejo_selecionado != 'Todos' else "Média Varejos"
    diferenca = seu_fat - media_outros
    st.metric(
        label, 
        R1(media_outros),
        delta=f"{'🔴' if diferenca < 0 else '🟢'} {R1(abs(diferenca))}" if seu_fat and media_outros else None
    )

with col3:
    st.metric(
        "Potencial Realista",
        R1(potencial_final),
        delta=f"📦 {produtos_cabiveis} produtos"
    )

# ========== TABS ==========
tab1, tab2, tab3, tab4 = st.tabs(["🛍️ O QUE COMPRAR", "📊 POR SEÇÃO", "🏪 POR VAREJO", "📈 TOP PRODUTOS"])

with tab1:
    st.subheader("Produtos que Outros Varejos Vendem e a Drogaria Brasil Não")
    
    if df_oportunidades.empty:
        st.warning("Nenhum produto encontrado.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            secoes = ['Todas'] + sorted(df_oportunidades['secao'].dropna().unique().tolist())
            secao_filtro = st.selectbox("Seção", secoes, key='secao_op')
        with col2:
            marcas = ['Todas'] + sorted(df_oportunidades['marca'].dropna().unique().tolist())
            marca_filtro = st.selectbox("Marca", marcas, key='marca_op')
        with col3:
            min_varejos = st.number_input("Mín. Varejos", 1, 50, 1)
        
        df = df_oportunidades.copy()
        if secao_filtro != 'Todas':
            df = df[df['secao'] == secao_filtro]
        if marca_filtro != 'Todas':
            df = df[df['marca'] == marca_filtro]
        df = df[df['varejos'] >= min_varejos]
        
        df_show = df.copy()
        df_show['Faturamento'] = df_show['faturamento'].apply(R1)
        df_show['Unidades'] = df_show['unidades'].apply(N)
        df_show['Preço Médio'] = df_show['preco_medio'].apply(R1)
        df_show['Varejos'] = df_show['varejos'].apply(N)
        
        st.dataframe(
            df_show[['produto', 'marca', 'secao', 'Faturamento', 'Unidades', 'Preço Médio', 'Varejos']],
            use_container_width=True,
            hide_index=True,
            height=500
        )
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total de Oportunidades", N(len(df)))
        with col2:
            st.metric("Faturamento Total Filtrado", R1(df['faturamento'].sum()))
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Lista Filtrada", csv, "produtos_para_comprar.csv")

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
        
        df_secoes['Oportunidade (R$)'] = df_secoes['faturamento_outros'] - df_secoes['faturamento_drogaria']
        df_secoes['Oportunidade (%)'] = ((df_secoes['faturamento_outros'] - df_secoes['faturamento_drogaria']) / 
                                         df_secoes['faturamento_outros'] * 100).round(1)
        df_secoes = df_secoes.sort_values('Oportunidade (R$)', ascending=False)
        
        df_show_secoes = df_secoes.copy()
        df_show_secoes['Seu Faturamento'] = df_show_secoes['faturamento_drogaria'].apply(R1)
        df_show_secoes['Faturamento Outros'] = df_show_secoes['faturamento_outros'].apply(R1)
        df_show_secoes['Oportunidade (R$)'] = df_show_secoes['Oportunidade (R$)'].apply(R1)
        df_show_secoes['Seus Produtos'] = df_show_secoes['produtos_drogaria'].apply(N)
        df_show_secoes['Produtos Outros'] = df_show_secoes['produtos_outros'].apply(N)
        
        st.dataframe(
            df_show_secoes[['secao', 'Seu Faturamento', 'Faturamento Outros', 'Oportunidade (R$)', 'Oportunidade (%)', 'Seus Produtos', 'Produtos Outros']],
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
            lambda x: f"{'🟢' if seu_fat > x else '🔴'} {R1(seu_fat - x)}" if seu_fat else R1(0)
        )
        df_show_varejos['Produtos'] = df_show_varejos['produtos'].apply(N)
        df_show_varejos['Unidades'] = df_show_varejos['unidades'].apply(N)
        
        st.dataframe(
            df_show_varejos[['varejo', 'Faturamento', 'Produtos', 'Unidades', 'Diferença']],
            use_container_width=True,
            hide_index=True,
            height=500
        )
        
        acima = len(df_resumo[df_resumo['faturamento'] > seu_fat])
        abaixo = len(df_resumo[df_resumo['faturamento'] < seu_fat])
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("🔴 Maiores que você", N(acima))
        with col2:
            st.metric("🟢 Menores que você", N(abaixo))
        
        todos_fat = pd.concat([pd.DataFrame({'varejo': ['DROGARIA BRASIL'], 'faturamento': [seu_fat]}), 
                               df_resumo[['varejo', 'faturamento']]])
        todos_fat = todos_fat.sort_values('faturamento', ascending=False).reset_index(drop=True)
        sua_posicao = todos_fat[todos_fat['varejo'] == 'DROGARIA BRASIL'].index[0] + 1
        st.info(f"🏆 Sua posição no ranking: **{sua_posicao}º** de {len(todos_fat)} varejos")

with tab4:
    st.subheader("Seus 10 Produtos Mais Vendidos")
    
    if df_top_produtos.empty:
        st.warning("Nenhum dado encontrado.")
    else:
        df_show_top = df_top_produtos.copy()
        df_show_top['Faturamento'] = df_show_top['faturamento'].apply(R1)
        df_show_top['Unidades'] = df_show_top['unidades'].apply(N)
        df_show_top['Preço Médio'] = df_show_top['preco_medio'].apply(R1)
        
        st.dataframe(
            df_show_top[['produto', 'Faturamento', 'Unidades', 'Preço Médio']],
            use_container_width=True,
            hide_index=True,
            height=400
        )
        
        st.caption("Compare com a aba 'O QUE COMPRAR' para ver produtos complementares")

st.markdown("---")
if periodo_de == 'TODOS':
    st.caption("Período: Todos | Fonte: REPORT_INFORMANTE_E_MERCADO")
else:
    st.caption(f"Período: {formatar_periodo(periodo_de)} até {formatar_periodo(periodo_ate)} | Fonte: REPORT_INFORMANTE_E_MERCADO")

conn.close()