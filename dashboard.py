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

st.title("🛒 O que Comprar para Melhorar as Vendas")
st.markdown("**DROGARIA BRASIL** | Comparação por varejos")

SUA_FARMACIA = "DROGARIA BRASIL"

@st.cache_data(ttl=3600)
def carregar_periodos():
    """Carrega lista de períodos disponíveis"""
    query_periodos = """
        SELECT DISTINCT "PER_MES" AS periodo
        FROM REPORT_INFORMANTE_E_MERCADO
        ORDER BY periodo DESC
    """
    df_periodos = pd.read_sql(query_periodos, engine)
    return df_periodos

@st.cache_data(ttl=3600)
def carregar_dados(periodo_selecionado):
    """Carrega todos os dados com ou sem filtro de período"""
    
    # Define filtro de período
    if periodo_selecionado == 'TODOS':
        filtro_periodo = ""
    else:
        filtro_periodo = f"AND \"PER_MES\" = '{periodo_selecionado}'"
    
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

# Filtro de período com opção TODOS
periodos_lista = ['TODOS'] + df_periodos['periodo'].tolist()
periodo_selecionado = st.sidebar.selectbox(
    "📅 Período:",
    periodos_lista,
    format_func=formatar_periodo,
    help="Selecione o mês/ano ou Todos para análise completa"
)

# Carregar dados com o período selecionado
df_resumo, df_seu, df_oportunidades, df_suas_secoes, df_outras_secoes, df_varejos, df_top_produtos = carregar_dados(periodo_selecionado)

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

st.sidebar.metric(
    "Faturamento", 
    R1(seu_fat),
    help=f"Soma de VAL_R$ no período: {formatar_periodo(periodo_selecionado)}"
)

st.sidebar.metric(
    "Produtos", 
    N(seus_produtos),
    help=f"Produtos distintos vendidos: {formatar_periodo(periodo_selecionado)}"
)

st.sidebar.metric(
    "Unidades", 
    N(suas_unidades),
    help=f"Total de unidades vendidas: {formatar_periodo(periodo_selecionado)}"
)

# ========== CARDS PRINCIPAIS ==========
st.markdown(f"### 📅 Período: {formatar_periodo(periodo_selecionado)}")
st.markdown("---")

col1, col2, col3 = st.columns(3)

if varejo_selecionado != 'Todos':
    media_outros = df_resumo[df_resumo['varejo'] == varejo_selecionado]['faturamento'].iloc[0] if not df_resumo[df_resumo['varejo'] == varejo_selecionado].empty else 0
else:
    media_outros = df_resumo['faturamento'].mean() if not df_resumo.empty else 0

potencial_bruto, potencial_penetracao, potencial_final, produtos_cabiveis = calcular_potencial_realista(df_oportunidades, seu_fat)

with col1:
    st.metric(
        "💰 Seu Faturamento", 
        R1(seu_fat),
        help=f"""
        **Fórmula:**  
        Soma de VAL_R$  
        WHERE INF_DESC = '{SUA_FARMACIA}'  
        Período: {formatar_periodo(periodo_selecionado)}
        """
    )

with col2:
    label = f"🏪 {varejo_selecionado}" if varejo_selecionado != 'Todos' else "🏪 Média Varejos"
    diferenca = seu_fat - media_outros
    
    if varejo_selecionado != 'Todos':
        help_text = f"""
        **Fórmula:**  
        Soma de VAL_R$  
        WHERE UTC_DESC_VAREJO = '{varejo_selecionado}'  
        Período: {formatar_periodo(periodo_selecionado)}
        """
    else:
        help_text = f"""
        **Fórmula:**  
        Média de VAL_R$ de todos varejos  
        Período: {formatar_periodo(periodo_selecionado)}  
        ({len(df_varejos)} varejos considerados)
        """
    
    st.metric(
        label, 
        R1(media_outros),
        delta=f"{'🔴' if diferenca < 0 else '🟢'} {R1(abs(diferenca))}" if seu_fat and media_outros else None,
        help=help_text
    )

with col3:
    st.metric(
        "💡 Potencial Realista",
        R1(potencial_final),
        delta=f"📦 {produtos_cabiveis} produtos",
        help=f"""
        **Fórmula passo a passo:**  
        
        1️⃣ **Potencial Bruto:** {R1(potencial_bruto)}  
        Soma de todo faturamento dos produtos ausentes
        
        2️⃣ **Com Penetração (70%):** {R1(potencial_penetracao)}  
        {R1(potencial_bruto)} × 0.70  
        (assume alcance de 70% do mercado)
        
        3️⃣ **Capacidade Máxima (20%):** {R1(seu_fat * 0.20)}  
        {R1(seu_fat)} × 0.20  
        (orçamento limitado a 20% do faturamento)
        
        4️⃣ **Resultado Final:** {R1(potencial_final)}  
        Menor valor entre (70% do Top 50) e (20% do seu faturamento)
        """
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
            min_varejos = st.number_input("Mín. Varejos", 1, 50, 1,
                help="Filtra produtos vendidos por pelo menos X varejos diferentes")
        
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
            height=500,
            column_config={
                'Preço Médio': st.column_config.TextColumn(
                    'Preço Médio', 
                    help='Faturamento Total ÷ Unidades Vendidas = Preço unitário médio'
                ),
                'Faturamento': st.column_config.TextColumn(
                    'Faturamento',
                    help='Soma de VAL_R$ para este produto em todos os varejos'
                ),
                'Unidades': st.column_config.TextColumn(
                    'Unidades',
                    help='Soma de VAL_UND (quantidade total vendida)'
                ),
                'Varejos': st.column_config.TextColumn(
                    'Varejos',
                    help='Quantos varejos diferentes vendem este produto'
                )
            }
        )
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "Total de Oportunidades", 
                N(len(df)),
                help="Quantidade de produtos encontrados com os filtros atuais"
            )
        with col2:
            st.metric(
                "Faturamento Total Filtrado", 
                R1(df['faturamento'].sum()),
                help="Soma do faturamento de todos os produtos listados acima"
            )
        
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
            height=500,
            column_config={
                'Oportunidade (R$)': st.column_config.TextColumn(
                    'Oportunidade (R$)',
                    help='Faturamento Outros - Seu Faturamento = Valor que deixou de ganhar'
                ),
                'Oportunidade (%)': st.column_config.TextColumn(
                    'Oportunidade (%)',
                    help='(Faturamento Outros - Seu Faturamento) ÷ Faturamento Outros × 100 = % de oportunidade'
                ),
                'Seus Produtos': st.column_config.TextColumn(
                    'Seus Produtos',
                    help='Quantos produtos diferentes você vende nesta seção'
                ),
                'Produtos Outros': st.column_config.TextColumn(
                    'Produtos Outros',
                    help='Quantos produtos diferentes os outros vendem nesta seção'
                )
            }
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
            height=500,
            column_config={
                'Faturamento': st.column_config.TextColumn(
                    'Faturamento',
                    help=f'Soma de VAL_R$ - Período: {formatar_periodo(periodo_selecionado)}'
                ),
                'Produtos': st.column_config.TextColumn(
                    'Produtos',
                    help='Quantidade de produtos diferentes vendidos'
                ),
                'Unidades': st.column_config.TextColumn(
                    'Unidades',
                    help='Quantidade total de unidades vendidas'
                ),
                'Diferença': st.column_config.TextColumn(
                    'Diferença',
                    help='Seu Faturamento - Faturamento do Varejo (🟢 você maior, 🔴 você menor)'
                )
            }
        )
        
        acima = len(df_resumo[df_resumo['faturamento'] > seu_fat])
        abaixo = len(df_resumo[df_resumo['faturamento'] < seu_fat])
        empatado = len(df_resumo[df_resumo['faturamento'] == seu_fat])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "🔴 Maiores que você", 
                N(acima),
                help="Varejos com faturamento total MAIOR que o seu"
            )
        with col2:
            st.metric(
                "🟢 Menores que você", 
                N(abaixo),
                help="Varejos com faturamento total MENOR que o seu"
            )
        with col3:
            st.metric(
                "⚪ Empate", 
                N(empatado),
                help="Varejos com faturamento IGUAL ao seu"
            )
        
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
            height=400,
            column_config={
                'Faturamento': st.column_config.TextColumn(
                    'Faturamento',
                    help=f'Soma de VAL_R$ - Período: {formatar_periodo(periodo_selecionado)}'
                ),
                'Unidades': st.column_config.TextColumn(
                    'Unidades',
                    help='Soma de VAL_UND (quantidade vendida)'
                ),
                'Preço Médio': st.column_config.TextColumn(
                    'Preço Médio',
                    help='Faturamento ÷ Unidades = Preço unitário médio'
                )
            }
        )
        
        st.caption("💡 Compare com a aba 'O QUE COMPRAR' para ver produtos complementares")

st.markdown("---")
st.caption(f"Período: {formatar_periodo(periodo_selecionado)} | Fonte: REPORT_INFORMANTE_E_MERCADO | Schema: DEMANDA")
st.caption(f"Total de períodos disponíveis: {len(df_periodos)}")

conn.close()