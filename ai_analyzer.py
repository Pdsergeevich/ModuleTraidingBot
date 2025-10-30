"""
Модуль ИИ-анализа новостей
Определяет контекст: положительный (long), отрицательный (short), нейтральный (range)
"""

import logging
import re
from typing import Dict, Optional
from openai import AsyncOpenAI
import anthropic

from config import Config

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """Класс для анализа новостей с помощью ИИ"""
    
    def __init__(self):
        """Инициализация ИИ-анализатора"""
        self.provider = Config.AI_PROVIDER
        
        if self.provider == 'openai':
            self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
            self.model = Config.OPENAI_MODEL
        elif self.provider == 'anthropic':
            self.client = anthropic.AsyncAnthropic(api_key=Config.ANTHROPIC_API_KEY)
            self.model = Config.ANTHROPIC_MODEL
        else:
            raise ValueError(f"Неподдерживаемый провайдер ИИ: {self.provider}")
        
        logger.info(f"✅ ИИ-анализатор инициализирован ({self.provider})")
    
    async def analyze_news(self, news_text: str, channel_name: str) -> Optional[Dict]:
        """
        Анализ новости с помощью ИИ для определения торгового контекста
        
        Args:
            news_text: Текст новости
            channel_name: Название канала
            
        Returns:
            Словарь с результатами анализа:
            - context: POSITIVE (long), NEGATIVE (short), NEUTRAL (range trading)
            - ticker: тикер инструмента
            - confidence: уверенность (0-1)
            - reasoning: объяснение
            - expected_impact: ожидаемая сила влияния
        """
        logger.info(f"🤖 ИИ-анализ новости из {channel_name}...")
        
        # Формируем промпт для ИИ
        prompt = self._create_analysis_prompt(news_text)
        
        try:
            # Получаем ответ от ИИ
            if self.provider == 'openai':
                response = await self._analyze_with_openai(prompt)
            else:
                response = await self._analyze_with_anthropic(prompt)
            
            # Парсим ответ ИИ
            analysis = self._parse_ai_response(response)
            
            if analysis:
                logger.info(
                    f"✅ ИИ-анализ завершен:\n"
                    f"   Инструмент: {analysis['ticker']}\n"
                    f"   Контекст: {analysis['context']}\n"
                    f"   Уверенность: {analysis['confidence']:.2%}\n"
                    f"   Сила влияния: {analysis['expected_impact']}\n"
                    f"   Объяснение: {analysis['reasoning'][:100]}..."
                )
            else:
                logger.info("ℹ️ Новость не релевантна для торговли")
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Ошибка при анализе новости: {e}")
            return None
    
    def _create_analysis_prompt(self, news_text: str) -> str:
        """
        Создание промпта для ИИ с учетом новой стратегии
        
        Args:
            news_text: Текст новости
            
        Returns:
            Промпт для ИИ
        """
        return f"""Ты - эксперт по финансовым рынкам и трейдингу. Проанализируй новость и определи:

ВАЖНО: Нужно определить КОНТЕКСТ новости для торговли:

1. **POSITIVE (Положительный)** - торговать в LONG (покупка):
   - Позитивные новости о компании (рост прибыли, новые контракты, одобрения и т.д.)
   - Благоприятные макроэкономические факторы
   - Ожидается восходящий тренд

2. **NEGATIVE (Отрицательный)** - торговать в SHORT (продажа):
   - Негативные новости о компании (убытки, скандалы, санкции и т.д.)
   - Неблагоприятные факторы
   - Ожидается нисходящий тренд

3. **NEUTRAL (Нейтральный)** - торговать в ДИАПАЗОНЕ (Range Trading):
   - Новость не имеет явного позитивного или негативного эффекта
   - Рынок консолидируется, движется боком
   - Нет четкого тренда
   - Подходит для покупки на минимумах дня и продажи на максимумах

Также определи:
- Тикер инструмента (SBER, GAZP, YNDX, LKOH, MOEX и т.д.)
- Уверенность в анализе (0-1)
- Ожидаемая сила влияния: LOW (слабое), MEDIUM (среднее), HIGH (сильное)

Новость: "{news_text}"

Ответь СТРОГО в следующем формате JSON:
{{
    "ticker": "SBER" или null если инструмент не определен,
    "context": "POSITIVE" или "NEGATIVE" или "NEUTRAL",
    "confidence": 0.85,
    "expected_impact": "HIGH" или "MEDIUM" или "LOW",
    "reasoning": "краткое объяснение на русском языке"
}}

Если новость не относится к конкретному торговому инструменту или не окажет влияния на цену, верни:
{{
    "ticker": null,
    "context": "NEUTRAL",
    "confidence": 0,
    "expected_impact": "LOW",
    "reasoning": "новость не релевантна для торговли"
}}"""
    
    async def _analyze_with_openai(self, prompt: str) -> str:
        """
        Анализ с помощью OpenAI
        
        Args:
            prompt: Промпт для анализа
            
        Returns:
            Ответ от ИИ
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Ты эксперт по финансовым рынкам и техническому анализу. "
                               "Твоя задача - определять торговый контекст новостей для алгоритмической торговли."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        return response.choices[0].message.content
    
    async def _analyze_with_anthropic(self, prompt: str) -> str:
        """
        Анализ с помощью Anthropic Claude
        
        Args:
            prompt: Промпт для анализа
            
        Returns:
            Ответ от ИИ
        """
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0.3,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
    
    def _parse_ai_response(self, response: str) -> Optional[Dict]:
        """
        Парсинг ответа ИИ
        
        Args:
            response: Ответ от ИИ
            
        Returns:
            Словарь с результатами или None
        """
        import json
        
        try:
            # Ищем JSON в ответе
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if not json_match:
                logger.warning("⚠️ JSON не найден в ответе ИИ")
                return None
            
            analysis = json.loads(json_match.group())
            
            # Проверяем обязательные поля
            if not analysis.get('ticker'):
                return None
            
            # Проверяем минимальную уверенность
            if analysis['confidence'] < Config.MIN_AI_CONFIDENCE:
                logger.info(
                    f"⚠️ Уверенность ИИ слишком низкая: {analysis['confidence']:.2%} "
                    f"(минимум: {Config.MIN_AI_CONFIDENCE:.2%})"
                )
                return None
            
            # Нормализуем контекст
            context = analysis['context'].upper()
            if context not in ['POSITIVE', 'NEGATIVE', 'NEUTRAL']:
                logger.warning(f"⚠️ Некорректный контекст: {context}")
                return None
            
            # Преобразуем контекст в направление для совместимости
            direction_map = {
                'POSITIVE': 'UP',
                'NEGATIVE': 'DOWN',
                'NEUTRAL': 'NEUTRAL'
            }
            
            return {
                'ticker': analysis['ticker'].upper(),
                'context': context,
                'direction': direction_map[context],  # Для обратной совместимости
                'confidence': float(analysis['confidence']),
                'expected_impact': analysis.get('expected_impact', 'MEDIUM'),
                'reasoning': analysis.get('reasoning', '')
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ответа ИИ: {e}")
            return None


if __name__ == '__main__':
    # Тестирование анализатора
    import asyncio
    
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        analyzer = AIAnalyzer()
        
        test_news = [
            "Сбербанк объявил о рекордной квартальной прибыли, превысившей ожидания аналитиков на 15%. Руководство повысило дивиденды.",
            "Газпром попал под новый пакет санкций ЕС. Ожидается существенное снижение экспортных доходов.",
            "Яндекс опубликовал квартальную отчетность. Результаты соответствуют ожиданиям рынка, без сюрпризов.",
            "ЦБ РФ сохранил ключевую ставку на уровне 16%. Решение было ожидаемо рынком."
        ]
        
        for news in test_news:
            print(f"\n{'='*60}")
            print(f"📰 Новость: {news}")
            result = await analyzer.analyze_news(news, "Test Channel")
            if result:
                print(f"   Тикер: {result['ticker']}")
                print(f"   Контекст: {result['context']}")
                print(f"   Уверенность: {result['confidence']:.2%}")
                print(f"   Сила влияния: {result['expected_impact']}")
                print(f"   Причина: {result['reasoning']}")
            else:
                print("   ❌ Новость не релевантна")
    
    asyncio.run(test())
