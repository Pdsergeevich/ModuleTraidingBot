"""
Модуль мониторинга рынка через Tinkoff Invest API
Расширенная версия с поддержкой исторических данных и определения трендов
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from decimal import Decimal

from tinkoff.invest import (
    AsyncClient,
    CandleInterval,
    GetLastPricesRequest,
)
from tinkoff.invest.utils import quotation_to_decimal

from config import Config
from technical_analysis import TechnicalAnalyzer

logger = logging.getLogger(__name__)


class MarketMonitor:
    """Класс для мониторинга рыночных котировок с техническим анализом"""
    
    def __init__(self, is_sandbox: bool = True):
        """
        Инициализация монитора рынка
        
        Args:
            is_sandbox: True - режим песочницы, False - боевой режим
        """
        self.token = Config.TINKOFF_TOKEN
        self.is_sandbox = is_sandbox
        self.client = None
        self.technical_analyzer = TechnicalAnalyzer()
        self.price_cache = {}
        self.candles_cache = {}  # Кэш исторических свечей
        
    async def __aenter__(self):
        """Асинхронный вход в контекст"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный выход из контекста"""
        await self.disconnect()
    
    async def connect(self):
        """Подключение к Tinkoff Invest API"""
        target = 'sandbox-invest-public-api.tinkoff.ru:443' if self.is_sandbox else 'invest-public-api.tinkoff.ru:443'
        self.client = AsyncClient(self.token, target=target)
        logger.info(f"✅ Подключение к Tinkoff API ({'песочница' if self.is_sandbox else 'боевой'})")
    
    async def disconnect(self):
        """Отключение от API"""
        if self.client:
            await self.client.close()
            logger.info("✅ Отключение от Tinkoff API")
    
    async def get_instrument_by_ticker(self, ticker: str) -> Optional[Dict]:
        """
        Получение информации об инструменте по тикеру
        
        Args:
            ticker: Тикер инструмента (например, SBER)
            
        Returns:
            Словарь с информацией об инструменте или None
        """
        try:
            instruments = await self.client.instruments.shares()
            
            for instrument in instruments.instruments:
                if instrument.ticker == ticker:
                    return {
                        'figi': instrument.figi,
                        'ticker': instrument.ticker,
                        'name': instrument.name,
                        'lot': instrument.lot,
                        'currency': instrument.currency,
                        'exchange': instrument.exchange,
                        'trading_status': instrument.trading_status,
                        'min_price_increment': quotation_to_decimal(instrument.min_price_increment)
                    }
            
            logger.warning(f"⚠️ Инструмент {ticker} не найден")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения инструмента {ticker}: {e}")
            return None
    
    async def get_current_price(self, figi: str) -> Optional[Decimal]:
        """
        Получение текущей цены инструмента
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            Текущая цена или None
        """
        try:
            response = await self.client.market_data.get_last_prices(figi=[figi])
            
            if response.last_prices:
                price = quotation_to_decimal(response.last_prices[0].price)
                self.price_cache[figi] = float(price)
                return price
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены: {e}")
            return None
    
    async def get_historical_candles(
        self,
        figi: str,
        days_back: int = None,
        interval: CandleInterval = CandleInterval.CANDLE_INTERVAL_1_MIN
    ) -> List[Dict]:
        """
        Получение исторических свечей для анализа
        
        Args:
            figi: FIGI инструмента
            days_back: Количество дней назад (по умолчанию из конфига)
            interval: Интервал свечей
            
        Returns:
            Список свечей
        """
        if days_back is None:
            days_back = Config.HISTORICAL_DAYS
        
        # Проверяем кэш
        cache_key = f"{figi}_{days_back}_{interval}"
        if cache_key in self.candles_cache:
            cache_time, cached_candles = self.candles_cache[cache_key]
            # Используем кэш, если данные не старше 5 минут
            if (datetime.now() - cache_time).seconds < 300:
                logger.info(f"📦 Использование кэшированных свечей для {figi}")
                return cached_candles
        
        try:
            candles = []
            from_date = datetime.now() - timedelta(days=days_back)
            to_date = datetime.now()
            
            logger.info(f"📊 Загрузка свечей для {figi} за {days_back} дней...")
            
            async for candle in self.client.get_all_candles(
                figi=figi,
                from_=from_date,
                to=to_date,
                interval=interval
            ):
                candles.append({
                    'time': candle.time,
                    'open': float(quotation_to_decimal(candle.open)),
                    'high': float(quotation_to_decimal(candle.high)),
                    'low': float(quotation_to_decimal(candle.low)),
                    'close': float(quotation_to_decimal(candle.close)),
                    'volume': candle.volume
                })
            
            # Сохраняем в кэш
            self.candles_cache[cache_key] = (datetime.now(), candles)
            
            logger.info(f"✅ Загружено {len(candles)} свечей")
            return candles
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения свечей: {e}")
            return []
    
    async def analyze_market_context(self, ticker: str, figi: str) -> Optional[Dict]:
        """
        Анализ рыночного контекста для инструмента
        Определяет волатильность, тренд, диапазоны
        
        Args:
            ticker: Тикер инструмента
            figi: FIGI инструмента
            
        Returns:
            Словарь с результатами анализа
        """
        logger.info(f"🔍 Анализ рыночного контекста для {ticker}...")
        
        # Получаем исторические данные
        candles = await self.get_historical_candles(figi, days_back=Config.HISTORICAL_DAYS)
        
        if not candles or len(candles) < Config.ATR_PERIOD + 1:
            logger.warning(f"⚠️ Недостаточно данных для анализа {ticker}")
            return None
        
        # Рассчитываем ATR (волатильность)
        atr = self.technical_analyzer.calculate_atr(candles)
        
        if not atr:
            logger.warning(f"⚠️ Не удалось рассчитать ATR для {ticker}")
            return None
        
        # Рассчитываем общую волатильность
        volatility = self.technical_analyzer.calculate_volatility(candles)
        
        # Проверяем допустимость волатильности
        if volatility < Config.MIN_VOLATILITY_PERCENT:
            logger.warning(f"⚠️ Слишком низкая волатильность: {volatility:.2f}%")
            return None
        
        if volatility > Config.MAX_VOLATILITY_PERCENT:
            logger.warning(f"⚠️ Слишком высокая волатильность: {volatility:.2f}%")
            return None
        
        # Получаем текущую цену
        current_price = await self.get_current_price(figi)
        if not current_price:
            return None
        
        current_price = float(current_price)
        
        # Определяем дневной диапазон для Range Trading
        daily_candles = [c for c in candles if c['time'].date() == datetime.now().date()]
        if not daily_candles:
            daily_candles = candles[-100:]  # Последние 100 свечей если сегодняшних нет
        
        daily_range = self.technical_analyzer.calculate_daily_range(daily_candles)
        
        # Определяем уровни поддержки и сопротивления
        levels = self.technical_analyzer.detect_support_resistance(candles)
        
        result = {
            'ticker': ticker,
            'figi': figi,
            'current_price': current_price,
            'atr': atr,
            'volatility_percent': volatility,
            'daily_range': daily_range,
            'support_levels': levels['support_levels'],
            'resistance_levels': levels['resistance_levels'],
            'candles': candles[-50:]  # Последние 50 свечей для дальнейшего анализа
        }
        
        logger.info(
            f"✅ Анализ завершен:\n"
            f"   Цена: {current_price:.2f}\n"
            f"   ATR: {atr:.4f}\n"
            f"   Волатильность: {volatility:.2f}%\n"
            f"   Дневной диапазон: {daily_range.get('width_percent', 0):.2f}%"
        )
        
        return result
    
    async def wait_for_pullback(
        self,
        ticker: str,
        figi: str,
        expected_direction: str,
        market_context: Dict,
        timeout: int = None
    ) -> Optional[Dict]:
        """
        Ожидание отката к уровням Фибоначчи для входа в позицию
        
        Args:
            ticker: Тикер инструмента
            figi: FIGI инструмента
            expected_direction: Ожидаемое направление (UP/DOWN)
            market_context: Контекст рынка с текущими данными
            timeout: Таймаут ожидания в секундах
            
        Returns:
            Словарь с результатами или None
        """
        if timeout is None:
            timeout = Config.PULLBACK_TIMEOUT
        
        logger.info(
            f"⏳ Ожидание отката для {ticker} (направление: {expected_direction}, "
            f"таймаут: {timeout}с)"
        )
        
        # Определяем начало и конец тренда для расчета уровней Фибоначчи
        candles = market_context['candles']
        current_price = market_context['current_price']
        
        # Находим значимое движение (начало тренда)
        trend_start_price = None
        trend_end_price = current_price
        
        if expected_direction == 'UP':
            # Ищем локальный минимум за последние свечи
            min_price = min(c['low'] for c in candles[-20:])
            trend_start_price = min_price
            
            # Проверяем минимальное движение тренда
            trend_movement = ((trend_end_price - trend_start_price) / trend_start_price) * 100
            if trend_movement < Config.MIN_TREND_MOVEMENT:
                logger.warning(f"⚠️ Недостаточное движение тренда: {trend_movement:.2f}%")
                return None
                
        else:  # DOWN
            # Ищем локальный максимум
            max_price = max(c['high'] for c in candles[-20:])
            trend_start_price = max_price
            
            trend_movement = ((trend_start_price - trend_end_price) / trend_start_price) * 100
            if trend_movement < Config.MIN_TREND_MOVEMENT:
                logger.warning(f"⚠️ Недостаточное движение тренда: {trend_movement:.2f}%")
                return None
        
        # Рассчитываем уровни Фибоначчи
        fibonacci_levels = self.technical_analyzer.calculate_fibonacci_levels(
            trend_start_price,
            trend_end_price,
            is_uptrend=(expected_direction == 'UP')
        )
        
        # Мониторим цену в поисках отката
        start_time = datetime.now()
        best_pullback = None
        
        while (datetime.now() - start_time).seconds < timeout:
            await asyncio.sleep(Config.UPDATE_INTERVAL)
            
            # Получаем текущую цену
            current_price_decimal = await self.get_current_price(figi)
            if not current_price_decimal:
                continue
            
            current_price = float(current_price_decimal)
            
            # Проверяем откат к уровням Фибоначчи
            pullback = self.technical_analyzer.detect_pullback(
                current_price,
                fibonacci_levels,
                is_uptrend=(expected_direction == 'UP')
            )
            
            if pullback:
                logger.info(
                    f"✅ Обнаружен откат к уровню {pullback['level']}% "
                    f"(цена: {current_price:.2f})"
                )
                
                return {
                    'success': True,
                    'ticker': ticker,
                    'figi': figi,
                    'entry_price': current_price,
                    'pullback_level': pullback['level'],
                    'fibonacci_levels': fibonacci_levels,
                    'trend_start': trend_start_price,
                    'trend_end': trend_end_price,
                    'atr': market_context['atr'],
                    'elapsed_time': (datetime.now() - start_time).seconds
                }
        
        logger.warning(f"⏰ Таймаут ожидания отката для {ticker}")
        return None
    
    async def monitor_range_trading_opportunity(
        self,
        ticker: str,
        figi: str,
        market_context: Dict,
        timeout: int = 300
    ) -> Optional[Dict]:
        """
        Мониторинг возможностей для Range Trading (нейтральный контекст)
        
        Args:
            ticker: Тикер инструмента
            figi: FIGI инструмента
            market_context: Контекст рынка
            timeout: Таймаут мониторинга
            
        Returns:
            Словарь с торговой возможностью или None
        """
        if not Config.ENABLE_RANGE_TRADING:
            logger.info("⚠️ Range Trading отключен в настройках")
            return None
        
        daily_range = market_context['daily_range']
        
        if not daily_range['valid']:
            logger.info("⚠️ Диапазон невалиден для Range Trading")
            return None
        
        logger.info(
            f"📊 Мониторинг Range Trading для {ticker}\n"
            f"   Диапазон: [{daily_range['low']:.2f} - {daily_range['high']:.2f}]\n"
            f"   Ширина: {daily_range['width_percent']:.2f}%"
        )
        
        range_width = daily_range['high'] - daily_range['low']
        offset = range_width * Config.RANGE_ENTRY_OFFSET
        
        # Вычисляем зоны входа
        buy_zone_max = daily_range['low'] + offset  # Покупаем около минимума
        sell_zone_min = daily_range['high'] - offset  # Продаем около максимума
        
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < timeout:
            await asyncio.sleep(Config.UPDATE_INTERVAL)
            
            current_price_decimal = await self.get_current_price(figi)
            if not current_price_decimal:
                continue
            
            current_price = float(current_price_decimal)
            
            # Проверяем зону покупки (около нижней границы)
            if current_price <= buy_zone_max:
                logger.info(
                    f"✅ Найдена возможность BUY в Range Trading\n"
                    f"   Цена: {current_price:.2f}\n"
                    f"   Зона входа: до {buy_zone_max:.2f}"
                )
                
                # Рассчитываем стопы для range trading
                stop_distance = range_width * Config.RANGE_STOP_PERCENT
                
                return {
                    'success': True,
                    'ticker': ticker,
                    'figi': figi,
                    'direction': 'UP',
                    'entry_price': current_price,
                    'stop_loss': current_price - stop_distance,
                    'take_profit': daily_range['high'] - offset,  # Целимся в верхнюю границу
                    'range_low': daily_range['low'],
                    'range_high': daily_range['high'],
                    'strategy': 'range_trading'
                }
            
            # Проверяем зону продажи (около верхней границы)
            elif current_price >= sell_zone_min:
                logger.info(
                    f"✅ Найдена возможность SELL в Range Trading\n"
                    f"   Цена: {current_price:.2f}\n"
                    f"   Зона входа: от {sell_zone_min:.2f}"
                )
                
                stop_distance = range_width * Config.RANGE_STOP_PERCENT
                
                return {
                    'success': True,
                    'ticker': ticker,
                    'figi': figi,
                    'direction': 'DOWN',
                    'entry_price': current_price,
                    'stop_loss': current_price + stop_distance,
                    'take_profit': daily_range['low'] + offset,  # Целимся в нижнюю границу
                    'range_low': daily_range['low'],
                    'range_high': daily_range['high'],
                    'strategy': 'range_trading'
                }
        
        logger.info(f"⏰ Таймаут мониторинга Range Trading для {ticker}")
        return None


if __name__ == '__main__':
    # Тестирование монитора
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        async with MarketMonitor(is_sandbox=True) as monitor:
            # Тест получения инструмента
            instrument = await monitor.get_instrument_by_ticker('SBER')
            if instrument:
                print(f"\n✅ Инструмент: {instrument['name']}")
                
                # Тест анализа рыночного контекста
                context = await monitor.analyze_market_context('SBER', instrument['figi'])
                if context:
                    print(f"\n✅ Контекст получен:")
                    print(f"   ATR: {context['atr']}")
                    print(f"   Волатильность: {context['volatility_percent']}%")
    
    asyncio.run(test())
