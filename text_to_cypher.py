"""Text-to-Cypher через YandexGPT."""
from openai import OpenAI
import os


class TextToCypher:
    def __init__(self, api_key: str, folder_id: str):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://llm.api.cloud.yandex.net/v1"
        )
        self.model_uri = f"gpt://{folder_id}/yandexgpt/latest"
    
    def generate_cypher(self, question: str, schema: str) -> str:
        """Генерация Cypher-запроса из естественного языка."""
        prompt = f"""Ты — эксперт по Neo4j и Cypher. Преобразуй вопрос на естественном языке в Cypher-запрос.

Схема графа:
{schema}

Вопрос: {question}

Верни ТОЛЬКО Cypher-запрос, без пояснений."""
        
        response = self.client.chat.completions.create(
            model=self.model_uri,
            messages=[
                {"role": "system", "content": "Ты — эксперт по Neo4j. Отвечай только Cypher-запросами."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        return response.choices[0].message.content.strip()