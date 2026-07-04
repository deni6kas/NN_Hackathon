"""
Семантический поиск узлов графа через vector index Neo4j (db.index.vector.queryNodes)
и эмбеддинг запроса от Yandex AI Studio (тип EMBEDDING_TYPE_QUERY — важно отличать
от EMBEDDING_TYPE_DOCUMENT, которым эмбеддились узлы: модели для запроса и документа разные).
"""
import logging
from typing import List, Optional

from neo4j import Driver

from embedder import QUERY, YandexEmbedder

logger = logging.getLogger(__name__)


def semantic_search(
    driver: Driver,
    embedder: YandexEmbedder,
    query_text: str,
    top_k: int = 10,
    vector_index_name: str = "node_embeddings",
    database: str = "neo4j",
    label_filter: Optional[str] = None,
) -> List[dict]:
    embedding = embedder.get_embedding(query_text, text_type=QUERY)
    if not embedding:
        return []

    label_clause = "WHERE $label IN labels(node)" if label_filter else ""
    cypher = f"""
    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
    YIELD node, score
    {label_clause}
    RETURN node.id AS id, node.name AS name, labels(node) AS labels,
           node.domain AS domain, node.description AS description, score
    ORDER BY score DESC
    """

    params = {"index_name": vector_index_name, "top_k": top_k, "embedding": embedding}
    if label_filter:
        params["label"] = label_filter

    with driver.session(database=database) as session:
        result = session.run(cypher, params)
        return [dict(r) for r in result]
