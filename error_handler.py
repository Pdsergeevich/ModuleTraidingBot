"""
Модуль обработки ошибок и мониторинга подключения к рынку
Автоматическое закрытие позиций при потере связи
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable
from dataclasses import dataclass

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class ConnectionStatus:
    """Статус подключения к рынку"""
    is_connected: bool = True
    last_update: datetime = None
    failed_attempts: int = 0
    last_price: Optional[float] = None
    last_error: Optional[str] = None


class MarketConnectionMonitor:
    """Монитор подключения к рынку с автоматическим управлением"""
    
    def __init__(self, on_connection_loss: Optional[Callable] = None):
        """
        Инициализация монитора
        
        Args:
            on_connection_loss: Callback при потере связи
        """
        self.status = ConnectionStatus(last_update=datetime.now())
        self.on_connection_loss = on_connection_loss
        self.is_monitoring = False
        
    def update_connection(self, price: Optional[float] = None, error: Optional[str] = None):
        """
        Обновление статуса подключения
        
        Args:
            price: Последняя полученная цена
            error: Ошибка (если есть)
        """
        if error:
            self.status.failed_attempts += 1
            self.status.last_error = error
            
            if self.status.failed_attempts >= Config.MAX_RETRY_ATTEMPTS:
                self.status.is_connected = False
                logger.error(
                    f"❌ ПОТЕРЯ СВЯЗИ С РЫНКОМ! "
                    f"Попыток: {self.status.failed_attempts}"
                )
                
                if self.on_connection_loss and Config.CLOSE_ON_CONNECTION_LOSS:
                    asyncio.create_task(self.on_connection_loss())
        else:
            # Успешное обновление
            self.status.is_connected = True
            self.status.last_update = datetime.now()
            self.status.failed_attempts = 0
            self.status.last_error = None
            
            if price:
                self.status.last_price = price
    
    def is_price_stale(self) -> bool:
        """
        Проверка устаревания данных
        
        Returns:
            True если данные устарели
        """
        if not self.status.last_update:
            return True
        
        time_since_update = (datetime.now() - self.status.last_update).seconds
        return time_since_update > Config.MAX_PRICE_STALE_TIME
    
    async def start_monitoring(self):
        """Запуск мониторинга устаревания данных"""
        self.is_monitoring = True
        logger.info("👀 Запуск мониторинга подключения к рынку...")
        
        while self.is_monitoring:
            await asyncio.sleep(10)
            
            if self.is_price_stale():
                logger.warning(
                    f"⚠️ Данные устарели! "
                    f"Последнее обновление: {self.status.last_update}"
                )
                
                if Config.CLOSE_ON_CONNECTION_LOSS and self.on_connection_loss:
                    logger.error("🚨 Закрытие позиций из-за устаревания данных!")
                    await self.on_connection_loss()
                    break
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.is_monitoring = False
        logger.info("🛑 Мониторинг подключения остановлен")


class SafeApiWrapper:
    """Обертка для безопасных API вызовов с retry логикой"""
    
    @staticmethod
    async def safe_call(func, *args, **kwargs):
        """
        Безопасный вызов функции с повторными попытками
        
        Args:
            func: Асинхронная функция для вызова
            *args, **kwargs: Аргументы функции
            
        Returns:
            Результат функции или None при ошибке
        """
        for attempt in range(Config.MAX_RETRY_ATTEMPTS):
            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=Config.API_TIMEOUT
                )
                return result
                
            except asyncio.TimeoutError:
                logger.warning(
                    f"⏰ Таймаут API вызова (попытка {attempt + 1}/{Config.MAX_RETRY_ATTEMPTS})"
                )
                if attempt < Config.MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(Config.RETRY_DELAY)
                    
            except Exception as e:
                logger.error(
                    f"❌ Ошибка API вызова: {e} "
                    f"(попытка {attempt + 1}/{Config.MAX_RETRY_ATTEMPTS})"
                )
                if attempt < Config.MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(Config.RETRY_DELAY)
        
        logger.error("❌ Исчерпаны все попытки API вызова")
        return None


# Декоратор для автоматической обработки ошибок
def handle_errors(func):
    """Декоратор для обработки ошибок в асинхронных функциях"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ Ошибка в {func.__name__}: {e}", exc_info=True)
            if Config.ALERT_ON_CRITICAL_ERRORS:
                logger.critical(f"🚨 КРИТИЧЕСКАЯ ОШИБКА в {func.__name__}!")
            return None
    return wrapper
