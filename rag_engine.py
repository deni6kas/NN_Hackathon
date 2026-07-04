"""RAG-генерация ответов."""
from openai import OpenAI
from neo4j import Driver
from embedder import YandexEmbedder, QUERY
from search import semantic_search


class RAGEngine:
    def __init__(self, driver: Driver, embedder: YandexEmbedder, api_key: str, folder_id: str):
        self.driver = driver
        self.embedder = embedder
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://llm.api.cloud.yandex.net/v1"
        )
        self.model_uri = f"gpt://{folder_id}/yandexgpt/latest"
    
    def answer_question(self, question: str, top_k: int = 5) -> str:
        """Генерация ответа на вопрос с использованием графа знаний."""
        # 1. Семантический поиск релевантных узлов
        results = semantic_search(
            self.driver, self.embedder, question,
            top_k=top_k
        )
        
        if not results:
            return "Не нашел информации по вашему вопросу в графе знаний."
        
        # 2. Собираем контекст
        context_parts = []
        for r in results:
            context_parts.append(f"- {r['name']}: {r.get('description', 'N/A')}")
        
        context = "\n".join(context_parts)
        
        # 3. Генерируем ответ через LLM
        prompt = f"""Ответь на вопрос, используя информацию из графа знаний.

Вопрос: {question}

Информация из графа:
{context}

Ответ:"""
        
        response = self.client.chat.completions.create(
            model=self.model_uri,
            messages=[
                {"role": "system", "content": "Ты — эксперт по горно-металлургической отрасли."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        answer = response.choices[0].message.content
        
        # 4. Добавляем источники
        sources = "\n\n**Источники:**\n" + "\n".join(f"- {r['name']}" for r in results[:3])
        
        return answer + sources