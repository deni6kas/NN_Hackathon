"""
Загрузка CSV (nodes.csv / edges.csv) в Neo4j батчами + расчёт эмбеддингов узлов.
Требуется плагин APOC Core (apoc.create.node / apoc.create.relationship).
"""
import logging
import re
from typing import Iterable, List

import pandas as pd
from neo4j import Driver

from .embedder import DOCUMENT, YandexEmbedder

logger = logging.getLogger(__name__)


def chunks(items: List[dict], size: int) -> Iterable[List[dict]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def sanitize_label(raw: str) -> str:
    """entity_type -> валидный лейбл Neo4j (буквы/цифры/подчёркивание, не начинается с цифры)."""
    raw = (raw or "Entity").strip()
    safe = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_]", "_", raw)
    if not safe or safe[0].isdigit():
        safe = f"E_{safe}"
    return safe


def sanitize_rel_type(raw: str) -> str:
    raw = (raw or "RELATED_TO").strip().upper()
    safe = re.sub(r"[^0-9A-ZА-ЯЁ_]", "_", raw)
    if not safe or safe[0].isdigit():
        safe = f"R_{safe}"
    return safe


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "да", "истина"}


class GraphImporter:
    def __init__(self, driver: Driver, database: str = "neo4j"):
        self.driver = driver
        self.database = database

    # ---------------------------------------------------------------- схема

    def init_schema(self, vector_index_name: str, vector_dimensions: int) -> None:
        """Уникальный constraint на id, вспомогательные индексы и vector index под эмбеддинги."""
        with self.driver.session(database=self.database) as session:
            session.run(
                "CREATE CONSTRAINT node_id_unique IF NOT EXISTS "
                "FOR (n:Node) REQUIRE n.id IS UNIQUE"
            )
            session.run(
                "CREATE INDEX node_domain_idx IF NOT EXISTS FOR (n:Node) ON (n.domain)"
            )
            session.run(
                "CREATE INDEX node_source_doc_idx IF NOT EXISTS "
                "FOR (n:Node) ON (n.source_document)"
            )
            session.run(
                f"""
                CREATE VECTOR INDEX {vector_index_name} IF NOT EXISTS
                FOR (n:Node) ON (n.embedding)
                OPTIONS {{
                  indexConfig: {{
                    `vector.dimensions`: {vector_dimensions},
                    `vector.similarity_function`: 'cosine'
                  }}
                }}
                """
            )
        logger.info("Constraint, индексы и vector index '%s' созданы", vector_index_name)

    # ------------------------------------------------------------- узлы

    def load_nodes(self, csv_path: str, batch_size: int = 500) -> int:
        df = pd.read_csv(csv_path, encoding="utf-8-sig").fillna("")
        rows = df.to_dict(orient="records")

        prepared = [
            {
                "id": str(row["node_id"]),
                "label": sanitize_label(str(row.get("entity_type", ""))),
                "name": row.get("name", ""),
                "language": row.get("language", ""),
                "synonyms": row.get("synonyms", ""),
                "description": row.get("description", ""),
                "domain": row.get("domain", ""),
                "source_document": row.get("source_document", ""),
                "is_canonical": to_bool(row.get("is_canonical", False)),
            }
            for row in rows
        ]

        query = """
        UNWIND $rows AS row
        CALL apoc.create.node([row.label, 'Node'], {
            id: row.id,
            name: row.name,
            language: row.language,
            synonyms: row.synonyms,
            description: row.description,
            domain: row.domain,
            source_document: row.source_document,
            is_canonical: row.is_canonical
        }) YIELD node
        RETURN count(node) AS created
        """

        total = 0
        with self.driver.session(database=self.database) as session:
            for batch in chunks(prepared, batch_size):
                created = session.execute_write(
                    lambda tx, rows=batch: tx.run(query, rows=rows).single()["created"]
                )
                total += created
                logger.info("Узлы: загружено %d / %d", total, len(prepared))

        return total

    # ------------------------------------------------------------- рёбра

    def load_edges(self, csv_path: str, batch_size: int = 500) -> int:
        df = pd.read_csv(csv_path, encoding="utf-8-sig").fillna("")
        rows = df.to_dict(orient="records")

        prepared = [
            {
                "source_id": str(row["source_id"]),
                "target_id": str(row["target_id"]),
                "rel_type": sanitize_rel_type(str(row.get("relationship_type", ""))),
                "weight": row.get("weight", 0) or 0,
                "conditions": row.get("conditions", ""),
                "verification_level": row.get("verification_level", ""),
                "confidence_level": row.get("confidence_level", ""),
                "source_document": row.get("source_document", ""),
            }
            for row in rows
        ]

        missing_query = """
        UNWIND $rows AS row
        OPTIONAL MATCH (source:Node {id: row.source_id})
        OPTIONAL MATCH (target:Node {id: row.target_id})
        WITH row, source, target
        WHERE source IS NULL OR target IS NULL
        RETURN count(row) AS missing
        """

        create_query = """
        UNWIND $rows AS row
        MATCH (source:Node {id: row.source_id})
        MATCH (target:Node {id: row.target_id})
        CALL apoc.create.relationship(source, row.rel_type, {
            weight: toFloat(row.weight),
            conditions: row.conditions,
            verification_level: row.verification_level,
            confidence_level: row.confidence_level,
            source_document: row.source_document
        }, target) YIELD rel
        RETURN count(rel) AS created
        """

        total = 0
        total_missing = 0
        with self.driver.session(database=self.database) as session:
            for batch in chunks(prepared, batch_size):
                missing = session.execute_read(
                    lambda tx, rows=batch: tx.run(missing_query, rows=rows).single()["missing"]
                )
                if missing:
                    total_missing += missing
                    logger.warning("В батче %d рёбер ссылаются на несуществующие узлы (пропущены)", missing)

                created = session.execute_write(
                    lambda tx, rows=batch: tx.run(create_query, rows=rows).single()["created"]
                )
                total += created
                logger.info("Рёбра: загружено %d / %d", total, len(prepared))

        if total_missing:
            logger.warning("Итого рёбер с отсутствующими source/target: %d", total_missing)

        return total

    # -------------------------------------------------------- эмбеддинги

    @staticmethod
    def _build_embedding_text(record: dict) -> str:
        parts = [record.get("name") or "", record.get("synonyms") or "", record.get("description") or ""]
        return ". ".join(p for p in parts if p).strip()

    def generate_embeddings(
        self,
        embedder: YandexEmbedder,
        batch_size: int = 200,
        max_workers: int = 5,
        force: bool = False,
    ) -> int:
        """
        Считает эмбеддинги для узлов (по умолчанию — только для тех, у кого их ещё нет)
        и сохраняет их в свойство n.embedding, которое покрыто vector index'ом.
        """
        where_clause = "" if force else "WHERE n.embedding IS NULL"
        fetch_query = f"""
        MATCH (n:Node)
        {where_clause}
        RETURN n.id AS id, n.name AS name, n.synonyms AS synonyms, n.description AS description
        """

        with self.driver.session(database=self.database) as session:
            records = [dict(r) for r in session.run(fetch_query)]

        logger.info("Нужно посчитать эмбеддинги для %d узлов", len(records))
        total = 0

        update_query = """
        UNWIND $rows AS row
        MATCH (n:Node {id: row.id})
        SET n.embedding = row.embedding
        RETURN count(n) AS updated
        """

        for batch in chunks(records, batch_size):
            texts = [self._build_embedding_text(r) for r in batch]
            embeddings = embedder.get_embeddings_bulk(texts, text_type=DOCUMENT, max_workers=max_workers)

            update_rows = [
                {"id": rec["id"], "embedding": emb} for rec, emb in zip(batch, embeddings) if emb
            ]
            if not update_rows:
                continue

            with self.driver.session(database=self.database) as session:
                updated = session.execute_write(
                    lambda tx, rows=update_rows: tx.run(update_query, rows=rows).single()["updated"]
                )
                total += updated
                logger.info("Эмбеддинги сохранены: %d / %d", total, len(records))

        return total
