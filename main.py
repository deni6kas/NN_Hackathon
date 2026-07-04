"""
CLI: инициализация схемы, импорт CSV в Neo4j, расчёт эмбеддингов, семантический поиск.

Примеры:
    python -m neo4j_importer init
    python -m neo4j_importer import-nodes --csv nodes.csv
    python -m neo4j_importer import-edges --csv edges.csv
    python -m neo4j_importer import-all
    python -m neo4j_importer embed
    python -m neo4j_importer search "лечение гипертонии" --top-k 5
"""
import argparse
import logging

from neo4j import GraphDatabase

from config import ImportConfig, Neo4jConfig, YandexConfig
from embedder import YandexEmbedder
from importer import GraphImporter
from search import semantic_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_driver(cfg: Neo4jConfig):
    driver = GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password))
    driver.verify_connectivity()
    return driver


def build_parser() -> argparse.ArgumentParser:
    import_cfg = ImportConfig()

    parser = argparse.ArgumentParser(
        description="Импорт CSV в Neo4j + семантический поиск через Yandex AI Studio"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Создать constraint/индексы (включая vector index)")

    p_nodes = sub.add_parser("import-nodes", help="Загрузить nodes.csv")
    p_nodes.add_argument("--csv", default=import_cfg.nodes_csv)

    p_edges = sub.add_parser("import-edges", help="Загрузить edges.csv")
    p_edges.add_argument("--csv", default=import_cfg.edges_csv)

    sub.add_parser("import-all", help="init + import-nodes + import-edges + embed (полный пайплайн)")

    p_embed = sub.add_parser("embed", help="Посчитать эмбеддинги для узлов без n.embedding")
    p_embed.add_argument("--force", action="store_true", help="Пересчитать эмбеддинги для всех узлов")

    p_search = sub.add_parser("search", help="Семантический поиск по узлам")
    p_search.add_argument("query")
    p_search.add_argument("--top-k", type=int, default=10)
    p_search.add_argument("--label", default=None, help="Ограничить поиск конкретным лейблом (entity_type)")

    return parser


def main() -> None:
    neo4j_cfg = Neo4jConfig()
    yandex_cfg = YandexConfig()
    import_cfg = ImportConfig()

    args = build_parser().parse_args()

    driver = build_driver(neo4j_cfg)
    importer = GraphImporter(driver, database=neo4j_cfg.database)

    try:
        if args.command == "init":
            importer.init_schema(import_cfg.vector_index_name, yandex_cfg.embedding_dimension)

        elif args.command == "import-nodes":
            n = importer.load_nodes(args.csv, batch_size=import_cfg.batch_size)
            logger.info("Готово: загружено узлов — %d", n)

        elif args.command == "import-edges":
            n = importer.load_edges(args.csv, batch_size=import_cfg.batch_size)
            logger.info("Готово: загружено рёбер — %d", n)

        elif args.command == "import-all":
            importer.init_schema(import_cfg.vector_index_name, yandex_cfg.embedding_dimension)
            importer.load_nodes(import_cfg.nodes_csv, batch_size=import_cfg.batch_size)
            importer.load_edges(import_cfg.edges_csv, batch_size=import_cfg.batch_size)
            embedder = YandexEmbedder(yandex_cfg.api_key, yandex_cfg.folder_id)
            importer.generate_embeddings(
                embedder,
                batch_size=import_cfg.embed_batch_size,
                max_workers=import_cfg.embed_max_workers,
            )
            logger.info("Полный пайплайн завершён")

        elif args.command == "embed":
            embedder = YandexEmbedder(yandex_cfg.api_key, yandex_cfg.folder_id)
            n = importer.generate_embeddings(
                embedder,
                batch_size=import_cfg.embed_batch_size,
                max_workers=import_cfg.embed_max_workers,
                force=args.force,
            )
            logger.info("Эмбеддинги посчитаны для %d узлов", n)

        elif args.command == "search":
            embedder = YandexEmbedder(yandex_cfg.api_key, yandex_cfg.folder_id)
            results = semantic_search(
                driver,
                embedder,
                args.query,
                top_k=args.top_k,
                vector_index_name=import_cfg.vector_index_name,
                database=neo4j_cfg.database,
                label_filter=args.label,
            )
            if not results:
                print("Ничего не найдено")
            for r in results:
                labels = ", ".join(r["labels"])
                print(f"{r['score']:.4f}  [{labels}]  {r['name']}  (id={r['id']})")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
