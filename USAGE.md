# Руководство: импорт CSV в Neo4j + семантический поиск (Yandex AI Studio)

Полная инструкция по запуску пакета `neo4j_importer` с нуля — от установки Neo4j
до первого семантического запроса.

---

## 1. Что понадобится

- Docker (или уже поднятый Neo4j 5.15+ с плагином APOC Core)
- Python 3.10+
- Аккаунт Yandex Cloud с доступом к Foundation Models (API-ключ + folder_id)
- Файлы `nodes.csv` и `edges.csv`

---

## 2. Поднять Neo4j

Проще всего через Docker:

```bash
docker run -d \
  --name neo4j-test \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/testpassword123 \
  -e NEO4J_PLUGINS='["apoc"]' \
  -e NEO4J_dbms_security_procedures_unrestricted=apoc.* \
  -v neo4j_data:/data \
  neo4j:5.26
```

Что тут происходит:
- `NEO4J_AUTH=neo4j/testpassword123` — логин/пароль (замени на свой)
- `NEO4J_PLUGINS='["apoc"]'` — автоматически ставит APOC при первом запуске
- `NEO4J_dbms_security_procedures_unrestricted=apoc.*` — разрешает вызывать `apoc.create.node` /
  `apoc.create.relationship`, без этого получишь `Procedure is not allowed`
- `-v neo4j_data:/data` — данные переживут перезапуск контейнера

Проверка, что всё поднялось:

```bash
docker logs neo4j-test --tail 20
```

Дождись строки `Started.`. Затем открой в браузере `http://localhost:7474`,
залогинься `neo4j` / `testpassword123`.

Если Neo4j уже есть (не через Docker) — просто убедись, что APOC Core установлен
и включён `apoc.*` в `neo4j.conf`, как описано выше.

---

## 3. Получить доступ к Yandex AI Studio

1. Зайди в [консоль Yandex Cloud](https://console.yandex.cloud/)
2. Создай (или используй существующий) каталог — его id — это `YANDEX_FOLDER_ID`
   (виден в URL консоли или в разделе «Обзор» каталога)
3. IAM → Сервисные аккаунты → создать сервисный аккаунт с ролью `ai.languageModels.user`
4. Создай API-ключ для этого сервисного аккаунта — это `YANDEX_API_KEY`

Если Foundation Models недоступны в каталоге — включи их в разделе Yandex AI Studio
в консоли.

---

## 4. Установить зависимости

```bash
cd neo4j_importer
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 5. Настроить `.env`

```bash
cp .env.example .env
```

Открой `.env` и заполни:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=testpassword123
NEO4J_DATABASE=neo4j

YANDEX_API_KEY=твой_api_key
YANDEX_FOLDER_ID=твой_folder_id
YANDEX_EMBEDDING_DIM=256

NODES_CSV=nodes.csv
EDGES_CSV=edges.csv
BATCH_SIZE=500
EMBED_BATCH_SIZE=200
EMBED_MAX_WORKERS=5
VECTOR_INDEX_NAME=node_embeddings
```

Про `YANDEX_EMBEDDING_DIM`: если Yandex обновит модель эмбеддингов и изменит
размерность вектора — поменяй это значение до `init`, иначе vector index
создастся с неверной размерностью и запись эмбеддингов будет падать.

---

## 6. Подготовить CSV

Положи `nodes.csv` и `edges.csv` в директорию `neo4j_importer` (или укажи путь
через `--csv` при запуске).

**`nodes.csv`** — обязательные колонки:

| колонка | описание |
|---|---|
| `node_id` | уникальный id узла |
| `entity_type` | становится доп. лейблом узла (все узлы также получают лейбл `Node`) |
| `name` | название |
| `language` | язык |
| `synonyms` | синонимы (текстом) |
| `description` | описание — используется для эмбеддинга |
| `domain` | домен/категория |
| `source_document` | источник |
| `is_canonical` | true/false |

**`edges.csv`** — обязательные колонки:

| колонка | описание |
|---|---|
| `source_id` | id узла-источника (должен совпадать с `node_id`) |
| `target_id` | id узла-цели |
| `relationship_type` | становится типом связи в Neo4j |
| `weight` | вес связи (число) |
| `conditions` | условия |
| `verification_level` | уровень верификации |
| `confidence_level` | уровень уверенности |
| `source_document` | источник |

Если своих CSV пока нет и хочется просто проверить пайплайн — скажи, соберу
маленький тестовый набор на 5-10 строк.

---

## 7. Запуск

Все команды выполняются из директории, где лежит папка `neo4j_importer`
(или из самой этой папки — смотря как удобнее с путями).

### 7.1. Полный пайплайн одной командой

```bash
python -m neo4j_importer import-all
```

Сделает по порядку: создаст constraint + индексы (включая vector index) →
загрузит `nodes.csv` → загрузит `edges.csv` → посчитает эмбеддинги для всех узлов.

### 7.2. Или по шагам (удобно для отладки)

```bash
# 1. Схема: constraint + индексы + vector index
python -m neo4j_importer init

# 2. Узлы
python -m neo4j_importer import-nodes --csv nodes.csv

# 3. Рёбра
python -m neo4j_importer import-edges --csv edges.csv

# 4. Эмбеддинги (только для узлов, у которых их ещё нет)
python -m neo4j_importer embed

# пересчитать эмбеддинги заново для всех узлов
python -m neo4j_importer embed --force
```

Ожидаемый вывод в консоли по ходу дела — примерно так:

```
2026-07-03 12:00:01 INFO Constraint, индексы и vector index 'node_embeddings' созданы
2026-07-03 12:00:03 INFO Узлы: загружено 500 / 1200
2026-07-03 12:00:05 INFO Узлы: загружено 1200 / 1200
2026-07-03 12:00:08 INFO Рёбра: загружено 500 / 2300
...
2026-07-03 12:01:40 INFO Нужно посчитать эмбеддинги для 1200 узлов
2026-07-03 12:01:55 INFO Эмбеддинги сохранены: 200 / 1200
...
2026-07-03 12:04:10 INFO Эмбеддинги посчитаны для 1200 узлов
```

### 7.3. Семантический поиск

```bash
python -m neo4j_importer search "гипертония" --top-k 5
```

Вывод:

```
0.8912  [Disease, Node]  Артериальная гипертензия  (id=d_0042)
0.8341  [Disease, Node]  Гипертонический криз  (id=d_0107)
0.7955  [Symptom, Node]  Повышенное давление  (id=s_0019)
...
```

Фильтр по конкретному лейблу (`entity_type`):

```bash
python -m neo4j_importer search "гипертония" --label Disease --top-k 5
```

---

## 8. Проверить результат глазами

Открой Neo4j Browser: `http://localhost:7474`.

```cypher
// посмотреть первые 25 узлов
MATCH (n:Node) RETURN n LIMIT 25

// посчитать узлы по лейблам
MATCH (n:Node) RETURN labels(n) AS labels, count(*) AS cnt ORDER BY cnt DESC

// проверить, что эмбеддинги записались
MATCH (n:Node) WHERE n.embedding IS NOT NULL RETURN count(n)

// проверить связи конкретного узла
MATCH (n:Node {id: 'd_0042'})-[r]-(m) RETURN n, r, m LIMIT 50

// список созданных индексов
SHOW INDEXES
```

`SHOW INDEXES` должен показать `node_id_unique` (constraint), `node_domain_idx`,
`node_source_doc_idx` и `node_embeddings` (тип `VECTOR`).

---

## 9. Частые проблемы

| Симптом | Причина / решение |
|---|---|
| `Procedure apoc.create.node not found` | APOC не установлен — проверь `NEO4J_PLUGINS` в Docker или установи вручную |
| `Procedure is not allowed` | не выставлен `dbms.security.procedures.unrestricted=apoc.*` |
| `There is no procedure with the name db.index.vector.queryNodes` | версия Neo4j < 5.13, обнови образ |
| Импорт рёбер логирует много "не найдены source/target" | в `edges.csv` есть `source_id`/`target_id`, которых нет в `nodes.csv` — проверь соответствие id, регистр, лишние пробелы |
| `ValueError: YANDEX_API_KEY и YANDEX_FOLDER_ID обязательны` | не заполнен `.env` или он не в той директории, откуда запускаешь скрипт |
| Частые `429` при `embed` | понизь `EMBED_MAX_WORKERS` в `.env` (например до 2-3) |
| `search` возвращает пусто | эмбеддинги ещё не посчитаны — сначала `embed`; либо `--top-k` слишком мал, либо запрос вообще не похож ни на один узел |

---

## 10. Если нужно начать с чистого листа

Удалить всё из базы (осторожно — необратимо):

```cypher
MATCH (n) DETACH DELETE n
```

Или полностью снести и пересоздать контейнер:

```bash
docker rm -f neo4j-test
docker volume rm neo4j_data
# и заново выполнить команду из шага 2
```

---

## 11. Структура пакета

```
neo4j_importer/
├── config.py     # чтение .env (Neo4jConfig, YandexConfig, ImportConfig)
├── embedder.py   # YandexEmbedder: get_embedding / get_embeddings_bulk
├── importer.py   # GraphImporter: init_schema, load_nodes, load_edges, generate_embeddings
├── search.py     # semantic_search через db.index.vector.queryNodes
├── main.py       # CLI: init / import-nodes / import-edges / import-all / embed / search
├── requirements.txt
├── .env.example
└── README.md
```
