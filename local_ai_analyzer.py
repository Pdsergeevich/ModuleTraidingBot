"""
Модуль анализа новостей с использованием локальной LLM через Ollama
Полностью бесплатно и без ограничений
"""

import logging
import json
import re
import requests
from typing import Dict, Optional

from config import Config

logger = logging.getLogger(__name__)


class LocalAIAnalyzer:
    """Анализатор новостей на базе локальной LLM (Ollama)"""
    
    def __init__(self, model: str = "llama3.2:3b", ollama_url: str = "http://localhost:11434"):
        """
        Инициализация локального ИИ-анализатора
        
        Args:
            model: Название модели в Ollama (llama3.2:3b, mistral, deepseek-r1 и т.д.)
            ollama_url: URL Ollama API
        """
        self.model = model
        self.ollama_url = ollama_url
        
        # Проверяем доступность Ollama
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                logger.info(f"✅ Локальный ИИ-анализатор инициализирован (модель: {model})")
                logger.info("💰 БЕСПЛАТНЫЙ режим - без лимитов и подписок!")
            else:
                logger.warning(f"⚠️ Ollama недоступен. Запустите: ollama serve")
        except Exception as e:
            logger.error(f"❌ Не удалось подключиться к Ollama: {e}")
            logger.info("📥 Установите Ollama: https://ollama.com/download")
    
    async def analyze_news(self, news_text: str, channel_name: str) -> Optional[Dict]:
        """
        Анализ новости с помощью локальной LLM
        
        Args:
            news_text: Текст новости
            channel_name: Название канала
            
        Returns:
            Словарь с результатами анализа
        """
        logger.info(f"🤖 [LOCAL] Анализ новости из {channel_name}...")
        
        prompt = self._create_analysis_prompt(news_text)
        
        try:
            # Отправляем запрос к Ollama
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 500
                    }
                },
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Ошибка Ollama API: {response.status_code}")
                return None
            
            result = response.json()
            ai_response = result.get('response', '')
            
            # Парсим ответ
            analysis = self._parse_ai_response(ai_response)
            
            if analysis:
                logger.info(
                    f"✅ [LOCAL] Анализ завершен:\n"
                    f"   Инструмент: {analysis['ticker']}\n"
                    f"   Контекст: {analysis['context']}\n"
                    f"   Уверенность: {analysis['confidence']:.2%}"
                )
            else:
                logger.info("ℹ️ [LOCAL] Новость не релевантна")
            
            return analysis
            
        except requests.exceptions.Timeout:
            logger.error("❌ Таймаут запроса к Ollama (модель слишком долго генерирует)")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка при анализе новости: {e}")
            return None
    
    def _create_analysis_prompt(self, news_text: str) -> str:
        """Создание промпта для локальной LLM"""
        return f"""Ты - эксперт по финансовым рынкам. Проанализируй новость и определи:

1. КОНТЕКСТ (один из трех):
   - POSITIVE - положительная новость, торговать в LONG (покупка)
   - NEGATIVE - негативная новость, торговать в SHORT (продажа)
   - NEUTRAL - нейтральная новость, торговать в диапазоне

2. ТИКЕР - российский инструмент: SBER, GAZP, YNDX, LKOH, MOEX и т.д.

3. УВЕРЕННОСТЬ - число от 0 до 1

4. СИЛА ВЛИЯНИЯ - LOW, MEDIUM или HIGH

5. ОБЪЯСНЕНИЕ - краткая причина

Новость: "{news_text}"

Ответь СТРОГО в JSON формате:
{{
    "ticker": "SBER",
    "context": "POSITIVE",
    "confidence": 0.85,
    "expected_impact": "HIGH",
    "reasoning": "объяснение"
}}

Если новость не относится к торговле, верни:
{{
    "ticker": null,
    "context": "NEUTRAL",
    "confidence": 0,
    "expected_impact": "LOW",
    "reasoning": "не релевантна"
}}"""
    
    def _parse_ai_response(self, response: str) -> Optional[Dict]:
        """Парсинг ответа локальной LLM (аналогично AIAnalyzer)"""
        try:
            # Ищем JSON в ответе
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if not json_match:
                logger.warning("⚠️ JSON не найден в ответе локальной LLM")
                return None
            
            analysis = json.loads(json_match.group())
            
            if not analysis.get('ticker'):
                return None
            
            if analysis['confidence'] < Config.MIN_AI_CONFIDENCE:
                logger.info(
                    f"⚠️ Уверенность локальной LLM слишком низкая: "
                    f"{analysis['confidence']:.2%}"
                )
                return None
            
            context = analysis['context'].upper()
            if context not in ['POSITIVE', 'NEGATIVE', 'NEUTRAL']:
                return None
            
            direction_map = {
                'POSITIVE': 'UP',
                'NEGATIVE': 'DOWN',
                'NEUTRAL': 'NEUTRAL'
            }
            
            return {
                'ticker': analysis['ticker'].upper(),
                'context': context,
                'direction': direction_map[context],
                'confidence': float(analysis['confidence']),
                'expected_impact': analysis.get('expected_impact', 'MEDIUM'),
                'reasoning': analysis.get('reasoning', '')
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ответа: {e}")
            return None


if __name__ == '__main__':
    # Тестирование локального анализатора
    import asyncio
    
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        analyzer = LocalAIAnalyzer(model="llama3.2:3b")
        
        test_news = "Сбербанк объявил о рекордной квартальной прибыли, превысившей ожидания на 15%"
        
        result = await analyzer.analyze_news(test_news, "Test")
        print(f"\nРезультат: {result}")
    
    asyncio.run(test())
