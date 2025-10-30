"""
Модуль мониторинга Telegram-каналов
Отслеживает новые сообщения и передает их на анализ
"""

import asyncio
from datetime import datetime
from typing import Callable, List, Dict
from telethon import TelegramClient, events
from telethon.tl.types import Message
import logging

from config import Config

logger = logging.getLogger(__name__)


class TelegramMonitor:
    """Класс для мониторинга Telegram-каналов в реальном времени"""
    
    def __init__(self, on_message_callback: Callable):
        """
        Инициализация монитора
        
        Args:
            on_message_callback: Функция, которая будет вызвана при получении нового сообщения
        """
        self.client = TelegramClient(
            Config.TELEGRAM_SESSION_NAME,
            Config.TELEGRAM_API_ID,
            Config.TELEGRAM_API_HASH
        )
        self.on_message_callback = on_message_callback
        self.channels = Config.TELEGRAM_CHANNELS
        self.is_running = False
        
    async def start(self):
        """Запуск мониторинга каналов"""
        logger.info("Запуск Telegram монитора...")
        
        # Подключаемся к Telegram
        await self.client.start()
        logger.info("✅ Успешное подключение к Telegram")
        
        # Получаем entity для каждого канала
        channel_entities = []
        for channel in self.channels:
            try:
                entity = await self.client.get_entity(channel)
                channel_entities.append(entity)
                logger.info(f"📡 Подписка на канал: {channel}")
            except Exception as e:
                logger.error(f"❌ Не удалось подписаться на {channel}: {e}")
        
        # Устанавливаем обработчик новых сообщений
        @self.client.on(events.NewMessage(chats=channel_entities))
        async def handler(event: events.NewMessage.Event):
            """Обработчик новых сообщений"""
            message_data = await self._parse_message(event.message)
            
            # Вызываем callback функцию для обработки сообщения
            await self.on_message_callback(message_data)
        
        self.is_running = True
        logger.info("🚀 Мониторинг запущен. Ожидание новостей...")
        
        # Держим соединение открытым
        await self.client.run_until_disconnected()
    
    async def _parse_message(self, message: Message) -> Dict:
        """
        Парсинг сообщения из Telegram
        
        Args:
            message: Объект сообщения Telegram
            
        Returns:
            Словарь с данными сообщения
        """
        # Получаем информацию о канале
        chat = await message.get_chat()
        channel_name = chat.title if hasattr(chat, 'title') else 'Unknown'
        channel_username = chat.username if hasattr(chat, 'username') else None
        
        return {
            'channel_name': channel_name,
            'channel_username': channel_username,
            'message_id': message.id,
            'text': message.text or '',
            'timestamp': message.date,
            'has_media': message.media is not None,
            'views': message.views or 0,
            'forwards': message.forwards or 0
        }
    
    async def stop(self):
        """Остановка мониторинга"""
        logger.info("Остановка Telegram монитора...")
        self.is_running = False
        await self.client.disconnect()
        logger.info("✅ Монитор остановлен")


class TelegramBacktester:
    """Класс для работы с историческими данными из Telegram"""
    
    def __init__(self, news_file: str):
        """
        Инициализация бэктестера
        
        Args:
            news_file: Путь к JSON файлу с историческими новостями
        """
        self.news_file = news_file
        self.news_data = []
        
    def load_historical_news(self) -> List[Dict]:
        """
        Загрузка исторических новостей из файла
        
        Returns:
            Список новостей
        """
        import json
        
        try:
            with open(self.news_file, 'r', encoding='utf-8') as f:
                self.news_data = json.load(f)
            logger.info(f"✅ Загружено {len(self.news_data)} исторических новостей")
            return self.news_data
        except FileNotFoundError:
            logger.warning(f"⚠️ Файл {self.news_file} не найден")
            return []
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки новостей: {e}")
            return []
    
    async def collect_historical_news(self, days_back: int = 30):
        """
        Сбор исторических сообщений из каналов
        
        Args:
            days_back: Количество дней назад для сбора
        """
        import json
        from datetime import timedelta
        
        client = TelegramClient(
            Config.TELEGRAM_SESSION_NAME,
            Config.TELEGRAM_API_ID,
            Config.TELEGRAM_API_HASH
        )
        
        await client.start()
        logger.info(f"Сбор новостей за последние {days_back} дней...")
        
        all_messages = []
        offset_date = datetime.now() - timedelta(days=days_back)
        
        for channel in Config.TELEGRAM_CHANNELS:
            try:
                entity = await client.get_entity(channel)
                logger.info(f"Загрузка сообщений из {channel}...")
                
                async for message in client.iter_messages(
                    entity,
                    offset_date=offset_date,
                    reverse=False
                ):
                    if message.text:
                        chat = await message.get_chat()
                        all_messages.append({
                            'channel_name': chat.title,
                            'channel_username': chat.username,
                            'message_id': message.id,
                            'text': message.text,
                            'timestamp': message.date.isoformat(),
                            'views': message.views or 0
                        })
                
                logger.info(f"✅ Загружено {len(all_messages)} сообщений из {channel}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при загрузке из {channel}: {e}")
        
        # Сохраняем в файл
        with open(self.news_file, 'w', encoding='utf-8') as f:
            json.dump(all_messages, f, ensure_ascii=False, indent=2)
        
        await client.disconnect()
        logger.info(f"✅ Всего собрано {len(all_messages)} новостей")
        return all_messages


if __name__ == '__main__':
    # Пример использования для сбора исторических данных
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        if len(sys.argv) > 1 and sys.argv[1] == 'collect':
            # Режим сбора исторических данных
            backtester = TelegramBacktester(Config.BACKTEST_NEWS_FILE)
            await backtester.collect_historical_news(days_back=30)
        else:
            # Тестовый режим мониторинга
            async def test_callback(message_data):
                print(f"\n📨 Новое сообщение из {message_data['channel_name']}:")
                print(f"   {message_data['text'][:100]}...")
            
            monitor = TelegramMonitor(test_callback)
            await monitor.start()
    
    asyncio.run(main())
