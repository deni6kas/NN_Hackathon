"""
Клиент для Foundation Models Text Embeddings API (Yandex AI Studio / Yandex Cloud).
Документация: https://yandex.cloud/ru/docs/foundation-models/text-embeddings/
"""
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DOCUMENT = "EMBEDDING_TYPE_DOCUMENT"
QUERY = "EMBEDDING_TYPE_QUERY"

# У Yandex действует лимит на длину текста для эмбеддинга — режем с запасом.
MAX_TEXT_LENGTH = 8000


class YandexEmbedder:
    URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"

    def __init__(self, api_key: str, folder_id: str, max_retries: int = 5, timeout: int = 30):
        if not api_key or not folder_id:
            raise ValueError("YANDEX_API_KEY и YANDEX_FOLDER_ID обязательны")

        self.api_key = api_key
        self.folder_id = folder_id
        self.timeout = timeout

        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1.5,
            status_forcelist=[500, 502, 503, 504],  # 429 обрабатываем вручную ниже
            allowed_methods=["POST"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _model_uri(self, text_type: str) -> str:
        model = "text-search-doc" if text_type == DOCUMENT else "text-search-query"
        return f"emb://{self.folder_id}/{model}/latest"

    def get_embedding(self, text: str, text_type: str = DOCUMENT) -> List[float]:
        """Синхронно получить эмбеддинг одного текста. Пустой текст -> пустой список."""
        text = (text or "").strip()
        if not text:
            return []

        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "x-folder-id": self.folder_id,
        }
        payload = {"modelUri": self._model_uri(text_type), "text": text[:MAX_TEXT_LENGTH]}

        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                resp = self.session.post(self.URL, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code == 429:
                    sleep_s = (2 ** attempt) + random.random()
                    logger.warning("429 от Yandex API, повтор через %.1fс", sleep_s)
                    time.sleep(sleep_s)
                    continue
                resp.raise_for_status()
                return resp.json()["embedding"]
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(1 + attempt)

        logger.error("Не удалось получить эмбеддинг после нескольких попыток: %s", last_exc)
        raise last_exc

    def get_embeddings_bulk(
        self,
        texts: List[str],
        text_type: str = DOCUMENT,
        max_workers: int = 5,
    ) -> List[Optional[List[float]]]:
        """
        Yandex API не поддерживает батчинг в одном HTTP-запросе, поэтому распараллеливаем
        через пул потоков с ограниченным числом воркеров (иначе легко упереться в rate limit).
        Порядок результатов соответствует порядку texts; ошибки -> None на этой позиции.
        """
        results: List[Optional[List[float]]] = [None] * len(texts)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_idx = {
                pool.submit(self.get_embedding, text, text_type): i for i, text in enumerate(texts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    logger.exception("Ошибка получения эмбеддинга для текста #%d", idx)
                    results[idx] = None

        return results
