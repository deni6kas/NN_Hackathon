"""Streamlit UI для графа знаний."""
from dotenv import load_dotenv  # импортируем функцию
load_dotenv()
import streamlit as st
import pandas as pd
from neo4j import GraphDatabase
from pyvis.network import Network
import streamlit.components.v1 as components
import os
from config import Neo4jConfig, YandexConfig
from embedder import YandexEmbedder, QUERY
from search import semantic_search


st.set_page_config(page_title="Граф знаний R&D", layout="wide")

# Инициализация
@st.cache_resource
# Стало:
# Убедись, что импорт os есть, или добавь его сюда

@st.cache_resource
def get_driver():
    # Напрямую вытаскиваем переменные из твоего .env файла
    # Если их там нет, подставятся стандартные настройки для локального Docker
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "12345678") # <-- укажи тут пароль из своего .env, если он другой
    
    return GraphDatabase.driver(uri, auth=(user, password))


@st.cache_resource
def get_embedder():
    cfg = YandexConfig()
    return YandexEmbedder(cfg.api_key, cfg.folder_id)


driver = get_driver()
embedder = get_embedder()


# Боковая панель
st.sidebar.title("🔬 Граф знаний R&D")
st.sidebar.markdown("---")

# Статистика графа
with driver.session() as session:
    stats = session.run("""
        MATCH (n) 
        RETURN labels(n)[0] AS type, count(n) AS count
        ORDER BY count DESC
    """).data()

st.sidebar.subheader("📊 Статистика графа")
for stat in stats:
    st.sidebar.metric(stat['type'], stat['count'])


# Главная страница
tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 Поиск", "🕸️ Визуализация", "📈 Аналитика", "💬 Чат с LLM"
])


# ===== TAB 1: СЕМАНТИЧЕСКИЙ ПОИСК =====
with tab1:
    st.header("Семантический поиск")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Введите запрос:", placeholder="Какие методы обессоливания воды...")
    with col2:
        top_k = st.slider("Количество результатов", 5, 50, 10)
        label_filter = st.selectbox(
            "Тип сущности", 
            ["Все", "Process", "Material", "Equipment", "Facility", "Experiment"]
        )
    
    if query:
        label = None if label_filter == "Все" else label_filter
        
        with st.spinner("Поиск..."):
            results = semantic_search(
                driver, embedder, query,
                top_k=top_k,
                label_filter=label
            )
        
        if results:
            st.success(f"Найдено {len(results)} результатов")
            
            for r in results:
                with st.expander(f"{r['name']} (score: {r['score']:.3f})"):
                    st.write(f"**Тип:** {', '.join(r['labels'])}")
                    st.write(f"**Домен:** {r.get('domain', 'N/A')}")
                    st.write(f"**Описание:** {r.get('description', 'N/A')}")
                    
                    # Показать связанные сущности
                    with driver.session() as session:
                        rels = session.run("""
                            MATCH (n {id: $id})-[r]-(m)
                            RETURN type(r) AS rel_type, m.name AS target_name, labels(m) AS target_labels
                            LIMIT 10
                        """, id=r['id']).data()
                        
                        if rels:
                            st.write("**Связи:**")
                            for rel in rels:
                                st.write(f"  • {rel['rel_type']} → {rel['target_name']}")
        else:
            st.warning("Ничего не найдено")


# ===== TAB 2: ВИЗУАЛИЗАЦИЯ ГРАФА =====
with tab2:
    st.header("Визуализация графа")
    
    center_node = st.text_input("Центральный узел (ID или название):", placeholder="PRO_1")
    
    if center_node:
        with st.spinner("Построение графа..."):
            with driver.session() as session:
                # Ищем узел
                result = session.run("""
                    MATCH (n)
                    WHERE n.id = $id OR n.name CONTAINS $id
                    RETURN n.id AS id, n.name AS name, labels(n) AS labels
                    LIMIT 1
                """, id=center_node).single()
                
                if result:
                    center_id = result['id']
                    
                    # Получаем подграф (2 уровня)
                    graph_data = session.run("""
                        MATCH path = (center {id: $id})-[*1..2]-(neighbor)
                        RETURN center, relationships(path), neighbor
                        LIMIT 100
                    """, id=center_id).data()
                    
                    # Строим граф через pyvis
                    net = Network(height="600px", width="100%", bgcolor="#222222", font_color="white")
                    net.barnes_hut()
                    
                    nodes_added = set()
                    
                    for item in graph_data:
                        center = item['center']
                        neighbor = item['neighbor']
                        
                        # Добавляем узлы
                        if center['id'] not in nodes_added:
                            net.add_node(
                                center['id'], 
                                label=center['name'], 
                                title=f"{center['name']}\n{', '.join(center['labels'])}",
                                color="#FF6B6B" if center['id'] == center_id else "#4ECDC4"
                            )
                            nodes_added.add(center['id'])
                        
                        if neighbor['id'] not in nodes_added:
                            net.add_node(
                                neighbor['id'], 
                                label=neighbor['name'],
                                title=f"{neighbor['name']}\n{', '.join(neighbor['labels'])}",
                                color="#4ECDC4"
                            )
                            nodes_added.add(neighbor['id'])
                    
                    # Добавляем рёбра
                    for item in graph_data:
                        for rel in item['relationships(path)']:
                            net.add_edge(rel.start_node.element_id, rel.end_node.element_id)
                    
                    # Рендерим
                    net.save_graph("graph.html")
                    with open("graph.html", "r", encoding="utf-8") as f:
                        html = f.read()
                    components.html(html, height=620)
                else:
                    st.warning("Узел не найден")


# ===== TAB 3: АНАЛИТИКА =====
with tab3:
    st.header("Аналитика и дашборды")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Топ доменов")
        with driver.session() as session:
            domains = session.run("""
                MATCH (n)
                WHERE n.domain IS NOT NULL AND n.domain <> ''
                RETURN n.domain AS domain, count(n) AS count
                ORDER BY count DESC
                LIMIT 10
            """).data()
            
            if domains:
                df = pd.DataFrame(domains)
                st.bar_chart(df.set_index('domain'))
    
    with col2:
        st.subheader("Источники данных")
        with driver.session() as session:
            sources = session.run("""
                MATCH (n)
                WHERE n.source_document IS NOT NULL AND n.source_document <> ''
                RETURN n.source_document AS source, count(n) AS count
                ORDER BY count DESC
                LIMIT 10
            """).data()
            
            if sources:
                df = pd.DataFrame(sources)
                st.bar_chart(df.set_index('source'))
    
    st.subheader("Противоречия")
    with driver.session() as session:
        contradictions = session.run("""
            MATCH (c:Contradiction)
            RETURN c.description AS description, c.resolution_status AS status
            LIMIT 10
        """).data()
        
        if contradictions:
            df = pd.DataFrame(contradictions)
            st.dataframe(df)
        else:
            st.info("Противоречий не найдено")


# ===== TAB 4: ЧАТ С LLM =====
with tab4:
    st.header("Чат с графом знаний")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("Задайте вопрос о графе знаний..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Думаю..."):
                # TODO: Text-to-Cypher + генерация ответа через LLM
                response = f"Это демо-ответ на вопрос: {prompt}\n\n(Здесь будет интеграция с YandexGPT для Text-to-Cypher и генерации ответа)"
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})