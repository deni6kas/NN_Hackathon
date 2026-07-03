# Датасет карты знаний R&D (горно-металлургическая отрасль) — beta

Граф знаний, извлечённый NLP-пайплайном (Yandex GPT) из корпуса внутренних
документов, отчётов и презентаций (PDF, DOCX/DOCM, PPTX). Данные представлены
в виде связанных таблиц: **узлы графа**, **связи между ними**, а также
сопутствующие таблицы параметров, экспертов, противоречий и метаданных документов.

> ⚠️ **beta / промежуточный срез.** Уровень достоверности по большинству записей —
> `Unverified` (автоматическое извлечение без ручной верификации). Данные
> продолжают накапливаться, объёмы могут вырасти.

## Модель данных

Ядро — направленный граф «сущность → связь → сущность»:

```
nodes  ──(node_id)──┐
                     ├──► edges         (source_id / target_id ссылаются на node_id)
                     ├──► parameters    (node_id  ссылается на node_id)
                     └──► contradictions (node_id_1 / node_id_2 ссылаются на node_id)

document_metadata ──(doc_name)──►  поле source_document во всех таблицах
experts ── самостоятельная таблица носителей экспертизы
```

Все ID — строковые с префиксом типа сущности (`PRO_`, `EQU_`, `MAT_`, `PAR_`, `EXP_`, `DOC_`, `CONTR_`).
Кодировка файлов — **UTF-8 с BOM** (`utf-8-sig`); разделитель — запятая.

---

## Таблицы

### 1. `nodes.csv` — сущности (узлы графа)

Ключевые объекты предметной области: материалы, процессы, оборудование, свойства,
эксперименты, публикации, эксперты, установки.

| Столбец | Описание |
|---|---|
| `node_id` | Уникальный идентификатор узла. Префикс = тип сущности (`PRO_`, `EQU_`, `MAT_`, ...) |
| `entity_type` | Тип сущности: `Material`, `Process`, `Equipment`, `Property`, `Experiment`, `Publication`, `Expert`, `Facility` |
| `name` | Название сущности |
| `language` | Язык названия: `ru` / `en` |
| `synonyms` | Синонимы и альтернативные обозначения (аббревиатуры, англ. термины), через запятую |
| `description` | Текстовое описание сущности |
| `domain` | Домен: гидрометаллургия, пирометаллургия, экология, переработка отходов, горные работы и др. |
| `source_document` | Имя документа-источника (связь с `document_metadata.doc_name`) |
| `created_date` | Дата первого появления записи (YYYY-MM-DD) |
| `updated_date` | Дата последнего обновления записи (YYYY-MM-DD) |
| `is_canonical` | `True`, если запись считается канонической (не дубль-синоним) |

### 2. `edges.csv` — связи между сущностями (рёбра графа)

Отношения вида «источник → тип связи → цель».

| Столбец | Описание |
|---|---|
| `source_id` | `node_id` исходной сущности |
| `target_id` | `node_id` целевой сущности |
| `relationship_type` | Тип связи: `uses_material`, `operates_at_condition`, `produces_output`, `described_in`, `validated_by`, `contradicts`, `researched_by`, `optimal_parameter` |
| `weight` | Численный вес связи (0–1); по умолчанию 0.5, при дедупликации берётся максимум |
| `bidirectional` | `True`, если найдена симметричная обратная связь |
| `conditions` | Условия применения связи (например, «pH: 7–8», «холодный климат») |
| `geographic_scope` | География: `Russia` / `Worldwide` / конкретные страны |
| `applicable_range` | Диапазон численных значений, при которых связь актуальна |
| `verification_level` | Уровень подтверждения: `Confirmed` / `Contradicted` / `Unverified` / `Partially_Confirmed` |
| `source_document` | Имя документа-источника |
| `confidence_level` | Уверенность извлечения: `High` / `Medium` / `Low` |
| `extraction_date` | Дата извлечения связи (YYYY-MM-DD) |

### 3. `parameters.csv` — численные параметры

Числовые характеристики сущностей (концентрации, температуры, скорости, доли и т.п.)
с единицами измерения и контекстом.

| Столбец | Описание |
|---|---|
| `parameter_id` | Уникальный идентификатор параметра (`PAR_...`) |
| `node_id` | `node_id` сущности, к которой относится параметр |
| `parameter_name` | Название параметра (концентрация, температура, скорость потока, pH, содержание ДМ...) |
| `unit` | Единица измерения (мг/л, °C, м³/ч, %, ...) |
| `value` | Точное значение (если задано одним числом) |
| `min_value` | Нижняя граница диапазона |
| `max_value` | Верхняя граница диапазона |
| `context` | Условия/контекст, при которых параметр актуален |
| `confidence_level` | Уверенность извлечения: `High` / `Medium` / `Low` |
| `source_document` | Имя документа-источника |
| `extraction_date` | Дата извлечения (YYYY-MM-DD) |

### 4. `experts.csv` — эксперты и носители компетенций

Люди и организации с областями экспертизы.

| Столбец | Описание |
|---|---|
| `expert_id` | Уникальный идентификатор эксперта (`EXP_...`) |
| `name` | ФИО или название организации/команды |
| `organization` | Организация |
| `country` | Страна |
| `expertise_node_ids` | Области экспертизы (темы/процессы/материалы), через запятую |
| `contact_email` | Контактный email (в beta обычно пусто) |
| `affiliation_year` | Год аффилиации (в beta обычно пусто) |
| `language` | Язык записи: `ru` / `en` |
| `verification_status` | Статус проверки: `Unverified` / `Verified` |

### 5. `contradictions.csv` — противоречия

Зафиксированные конфликты интерпретаций между источниками.

| Столбец | Описание |
|---|---|
| `contradiction_id` | Уникальный идентификатор противоречия (`CONTR_...`) |
| `node_id_1` | `node_id` первой конфликтующей сущности (может быть пусто) |
| `node_id_2` | `node_id` второй конфликтующей сущности (может быть пусто) |
| `relationship_type` | Тип связи, всегда `contradicts` |
| `description` | Описание сути противоречия |
| `conflicting_sources` | Документы-источники противоречия (через `\|`, если их несколько) |
| `resolution_status` | Статус разрешения: `open` / `resolved` |

### 6. `document_metadata.csv` — метаданные документов

Реестр обработанных исходных документов.

| Столбец | Описание |
|---|---|
| `doc_id` | Уникальный идентификатор документа (`DOC_...`) |
| `doc_name` | Имя файла (ключ для поля `source_document` в остальных таблицах) |
| `doc_type` | Формат: `PDF` / `DOCX` / `DOCM` / `PPTX` |
| `authors` | Авторы (в beta обычно пусто) |
| `publication_year` | Год публикации (в beta обычно пусто) |
| `publication_venue` | Издание/площадка публикации (в beta обычно пусто) |
| `country_origin` | Страна происхождения документа |
| `language` | Язык документа: `ru` / `en` |
| `relevance_tags` | Тематические теги (в beta обычно пусто) |
| `access_level` | Уровень доступа: `internal` / `public` / ... |
| `import_date` | Дата импорта документа (YYYY-MM-DD) |
| `verification_status` | Статус проверки: `Unverified` / `Verified` |

---

## Как пользоваться

- **Построить граф:** узлы — из `nodes.csv` (ключ `node_id`), рёбра — из `edges.csv`
  (`source_id` → `target_id`). Подходит для Neo4j / NetworkX и т.п.
- **Найти параметры сущности:** `parameters.csv WHERE node_id = <id>`.
- **Отследить источник любого факта:** поле `source_document` → строка в
  `document_metadata.csv` по `doc_name`.
- **Фильтрация по достоверности:** `verification_level` / `confidence_level`
  (в beta преобладает `Unverified` / `High`-по-умолчанию).

### Пример (Python / pandas)

```python
import pandas as pd

nodes = pd.read_csv("nodes.csv")
edges = pd.read_csv("edges.csv")

# связи с названиями сущностей вместо id
g = (edges
     .merge(nodes[["node_id", "name"]], left_on="source_id",  right_on="node_id")
     .merge(nodes[["node_id", "name"]], left_on="target_id",  right_on="node_id",
            suffixes=("_source", "_target")))
print(g[["name_source", "relationship_type", "name_target"]].head())
```
