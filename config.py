"""
Конфигурация приложения. Все параметры читаются из переменных окружения
(можно положить их в .env — см. .env.example).
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass
class Neo4jConfig:
    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))
    database: str = field(default_factory=lambda: os.getenv("NEO4J_DATABASE", "neo4j"))


@dataclass
class YandexConfig:
    api_key: str = field(default_factory=lambda: os.getenv("YANDEX_API_KEY", ""))
    folder_id: str = field(default_factory=lambda: os.getenv("YANDEX_FOLDER_ID", ""))
    # Размерность вектора у text-search-doc/query — 256. Если Yandex поменяет модель,
    # поменяйте и это значение (индекс в Neo4j должен совпадать по размерности).
    embedding_dimension: int = field(default_factory=lambda: _env_int("YANDEX_EMBEDDING_DIM", 256))


@dataclass
class ImportConfig:
    nodes_csv: str = field(default_factory=lambda: os.getenv("NODES_CSV", "nodes.csv"))
    edges_csv: str = field(default_factory=lambda: os.getenv("EDGES_CSV", "edges.csv"))
    batch_size: int = field(default_factory=lambda: _env_int("BATCH_SIZE", 500))
    embed_batch_size: int = field(default_factory=lambda: _env_int("EMBED_BATCH_SIZE", 200))
    embed_max_workers: int = field(default_factory=lambda: _env_int("EMBED_MAX_WORKERS", 5))
    vector_index_name: str = field(default_factory=lambda: os.getenv("VECTOR_INDEX_NAME", "node_embeddings"))
