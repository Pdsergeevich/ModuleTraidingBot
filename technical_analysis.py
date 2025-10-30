"""
Модуль технического анализа
Расчет индикаторов: ATR, уровни Фибоначчи, support/resistance, определение откатов
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from config import Config

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """Класс для технического анализа и расчета индикаторов"""
    
    def __init__(self):
        """Инициализация анализатора"""
        self.atr_period = Config.ATR_PERIOD
        
    def calculate_atr(self, candles: List[Dict]) -> Optional[float]:
        """
        Расчет Average True Range (ATR) - индикатора волатильности
        
        Args:
            candles: Список свечей с полями open, high, low, close
            
        Returns:
            Значение ATR или None
        """
        if len(candles) < self.atr_period + 1:
            logger.warning(f"Недостаточно данных для расчета ATR (нужно минимум {self.atr_period + 1})")
            return None
        
        try:
            # Создаем DataFrame из свечей
            df = pd.DataFrame(candles)
            
            # Расчет True Range
            # TR = max(High - Low, |High - Previous Close|, |Low - Previous Close|)
            df['high_low'] = df['high'] - df['low']
            df['high_prev_close'] = abs(df['high'] - df['close'].shift(1))
            df['low_prev_close'] = abs(df['low'] - df['close'].shift(1))
            
            df['true_range'] = df[['high_low', 'high_prev_close', 'low_prev_close']].max(axis=1)
            
            # Расчет ATR используя Wilder's smoothing (RMA)
            # RMA похожа на EMA, но с alpha = 1/period
            atr = df['true_range'].ewm(
                alpha=1/self.atr_period,
                adjust=False
            ).mean().iloc[-1]
            
            logger.info(f"📊 Рассчитан ATR: {atr:.4f}")
            return float(atr)
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета ATR: {e}")
            return None
    
    def calculate_fibonacci_levels(
        self,
        trend_start_price: float,
        trend_end_price: float,
        is_uptrend: bool
    ) -> Dict[str, float]:
        """
        Расчет уровней Фибоначчи для откатов
        
        Args:
            trend_start_price: Цена начала тренда
            trend_end_price: Цена окончания тренда
            is_uptrend: True если восходящий тренд, False если нисходящий
            
        Returns:
            Словарь с уровнями Фибоначчи
        """
        # Вычисляем диапазон движения
        price_range = abs(trend_end_price - trend_start_price)
        
        # Стандартные уровни Фибоначчи для откатов
        fib_levels = {
            '0.0': trend_end_price,
            '23.6': None,
            '38.2': None,
            '50.0': None,
            '61.8': None,
            '78.6': None,
            '100.0': trend_start_price
        }
        
        # Рассчитываем промежуточные уровни
        for level_name in ['23.6', '38.2', '50.0', '61.8', '78.6']:
            level_percent = float(level_name) / 100.0
            
            if is_uptrend:
                # В восходящем тренде откаты идут вниз
                fib_levels[level_name] = trend_end_price - (price_range * level_percent)
            else:
                # В нисходящем тренде откаты идут вверх
                fib_levels[level_name] = trend_end_price + (price_range * level_percent)
        
        logger.info(f"📐 Уровни Фибоначчи рассчитаны: {is_uptrend and 'восходящий' or 'нисходящий'} тренд")
        for level, price in fib_levels.items():
            if price:
                logger.info(f"   {level}%: {price:.2f}")
        
        return fib_levels
    
    def detect_pullback(
        self,
        current_price: float,
        fibonacci_levels: Dict[str, float],
        is_uptrend: bool
    ) -> Optional[Dict]:
        """
        Определение отката к уровням Фибоначчи
        
        Args:
            current_price: Текущая цена
            fibonacci_levels: Рассчитанные уровни Фибоначчи
            is_uptrend: Тип тренда
            
        Returns:
            Словарь с информацией об откате или None
        """
        tolerance_percent = Config.FIBONACCI_TOLERANCE / 100.0
        
        # Проверяем близость к ключевым уровням входа
        for level_percent in Config.FIBONACCI_ENTRY_LEVELS:
            level_key = f"{level_percent * 100:.1f}"
            
            if level_key not in fibonacci_levels:
                continue
            
            level_price = fibonacci_levels[level_key]
            if not level_price:
                continue
            
            # Вычисляем допустимое отклонение
            tolerance = level_price * tolerance_percent
            
            # Проверяем попадание в диапазон
            if abs(current_price - level_price) <= tolerance:
                logger.info(
                    f"✅ Обнаружен откат к уровню Фибоначчи {level_key}% "
                    f"(цена: {current_price:.2f}, уровень: {level_price:.2f})"
                )
                
                return {
                    'detected': True,
                    'level': level_key,
                    'level_price': level_price,
                    'current_price': current_price,
                    'deviation': abs(current_price - level_price),
                    'deviation_percent': (abs(current_price - level_price) / level_price) * 100
                }
        
        return None
    
    def calculate_daily_range(self, candles: List[Dict]) -> Dict:
        """
        Расчет дневного диапазона цен (для Range Trading)
        
        Args:
            candles: Список свечей за последний день
            
        Returns:
            Словарь с информацией о диапазоне
        """
        if not candles:
            return {'valid': False}
        
        df = pd.DataFrame(candles)
        
        # Находим максимум и минимум дня
        daily_high = df['high'].max()
        daily_low = df['low'].min()
        daily_close = df['close'].iloc[-1]
        
        # Вычисляем ширину диапазона
        range_width = daily_high - daily_low
        range_width_percent = (range_width / daily_low) * 100
        
        # Определяем середину диапазона
        range_middle = (daily_high + daily_low) / 2
        
        # Проверяем валидность диапазона
        valid_range = (
            Config.MIN_RANGE_WIDTH_PERCENT <= range_width_percent <= Config.MAX_RANGE_WIDTH_PERCENT
        )
        
        result = {
            'valid': valid_range,
            'high': daily_high,
            'low': daily_low,
            'middle': range_middle,
            'width': range_width,
            'width_percent': range_width_percent,
            'current_position': (daily_close - daily_low) / range_width if range_width > 0 else 0.5
        }
        
        if valid_range:
            logger.info(
                f"📊 Дневной диапазон: [{daily_low:.2f} - {daily_high:.2f}] "
                f"(ширина: {range_width_percent:.2f}%)"
            )
        else:
            logger.info(f"⚠️ Диапазон невалиден для торговли (ширина: {range_width_percent:.2f}%)")
        
        return result
    
    def detect_support_resistance(self, candles: List[Dict], window: int = 5) -> Dict:
        """
        Определение уровней поддержки и сопротивления
        
        Args:
            candles: Список свечей
            window: Размер окна для поиска локальных экстремумов
            
        Returns:
            Словарь с уровнями поддержки и сопротивления
        """
        if len(candles) < window * 3:
            return {'support_levels': [], 'resistance_levels': []}
        
        df = pd.DataFrame(candles)
        
        support_levels = []
        resistance_levels = []
        
        # Разбиваем данные на сегменты
        num_segments = len(df) // window
        
        for i in range(num_segments):
            segment = df.iloc[i * window:(i + 1) * window]
            
            # Находим минимум (потенциальная поддержка)
            min_price = segment['low'].min()
            support_levels.append(min_price)
            
            # Находим максимум (потенциальное сопротивление)
            max_price = segment['high'].max()
            resistance_levels.append(max_price)
        
        # Группируем близкие уровни (в пределах 1.5%)
        def cluster_levels(levels, tolerance=0.015):
            if not levels:
                return []
            
            levels = sorted(levels)
            clustered = []
            current_cluster = [levels[0]]
            
            for level in levels[1:]:
                if (level - current_cluster[-1]) / current_cluster[-1] <= tolerance:
                    current_cluster.append(level)
                else:
                    clustered.append(np.mean(current_cluster))
                    current_cluster = [level]
            
            clustered.append(np.mean(current_cluster))
            return clustered
        
        support_levels = cluster_levels(support_levels)
        resistance_levels = cluster_levels(resistance_levels)
        
        logger.info(f"📍 Найдено {len(support_levels)} уровней поддержки")
        logger.info(f"📍 Найдено {len(resistance_levels)} уровней сопротивления")
        
        return {
            'support_levels': support_levels,
            'resistance_levels': resistance_levels
        }
    
    def calculate_adaptive_stops(
        self,
        entry_price: float,
        atr: float,
        direction: str
    ) -> Dict:
        """
        Расчет адаптивных stop-loss и take-profit на основе ATR
        
        Args:
            entry_price: Цена входа
            atr: Значение ATR
            direction: Направление позиции (UP/DOWN)
            
        Returns:
            Словарь с уровнями стопов
        """
        # Рассчитываем базовые стопы на основе ATR
        stop_distance = atr * Config.ATR_STOP_MULTIPLIER
        take_distance = atr * Config.ATR_TAKE_MULTIPLIER
        
        # Переводим в проценты для проверки границ
        stop_percent = (stop_distance / entry_price) * 100
        take_percent = (take_distance / entry_price) * 100
        
        # Применяем минимальные и максимальные ограничения
        stop_percent = max(Config.MIN_STOP_LOSS_PERCENT, 
                          min(stop_percent, Config.MAX_STOP_LOSS_PERCENT))
        
        # Пересчитываем расстояния с учетом ограничений
        stop_distance = entry_price * (stop_percent / 100)
        
        # Вычисляем уровни
        if direction == 'UP':
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + take_distance
        else:  # DOWN
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - take_distance
        
        # Проверяем Risk/Reward соотношение
        risk_reward_ratio = take_distance / stop_distance
        
        logger.info(
            f"🎯 Адаптивные стопы (ATR={atr:.4f}):\n"
            f"   Entry: {entry_price:.2f}\n"
            f"   Stop-Loss: {stop_loss:.2f} (-{stop_percent:.2f}%)\n"
            f"   Take-Profit: {take_profit:.2f} (+{take_percent:.2f}%)\n"
            f"   Risk/Reward: 1:{risk_reward_ratio:.2f}"
        )
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'stop_distance': stop_distance,
            'take_distance': take_distance,
            'stop_percent': stop_percent,
            'take_percent': take_percent,
            'risk_reward_ratio': risk_reward_ratio,
            'atr_value': atr
        }
    
    def calculate_volatility(self, candles: List[Dict]) -> float:
        """
        Расчет волатильности на основе стандартного отклонения доходности
        
        Args:
            candles: Список свечей
            
        Returns:
            Волатильность в процентах
        """
        if len(candles) < 2:
            return 0.0
        
        df = pd.DataFrame(candles)
        
        # Рассчитываем доходность
        df['returns'] = df['close'].pct_change()
        
        # Стандартное отклонение доходности
        volatility = df['returns'].std() * 100
        
        logger.info(f"📊 Волатильность: {volatility:.2f}%")
        
        return float(volatility)


if __name__ == '__main__':
    # Тестирование анализатора
    logging.basicConfig(level=logging.INFO)
    
    # Создаем тестовые данные
    test_candles = [
        {'open': 100, 'high': 105, 'low': 98, 'close': 103, 'volume': 1000},
        {'open': 103, 'high': 107, 'low': 101, 'close': 106, 'volume': 1100},
        {'open': 106, 'high': 110, 'low': 104, 'close': 108, 'volume': 1200},
        {'open': 108, 'high': 112, 'low': 106, 'close': 110, 'volume': 1300},
        {'open': 110, 'high': 115, 'low': 108, 'close': 113, 'volume': 1400},
        {'open': 113, 'high': 118, 'low': 111, 'close': 116, 'volume': 1500},
        {'open': 116, 'high': 120, 'low': 114, 'close': 118, 'volume': 1600},
        {'open': 118, 'high': 122, 'low': 116, 'close': 120, 'volume': 1700},
        {'open': 120, 'high': 125, 'low': 118, 'close': 123, 'volume': 1800},
        {'open': 123, 'high': 128, 'low': 121, 'close': 126, 'volume': 1900},
        {'open': 126, 'high': 130, 'low': 124, 'close': 128, 'volume': 2000},
        {'open': 128, 'high': 132, 'low': 126, 'close': 130, 'volume': 2100},
        {'open': 130, 'high': 135, 'low': 128, 'close': 133, 'volume': 2200},
        {'open': 133, 'high': 138, 'low': 131, 'close': 136, 'volume': 2300},
        {'open': 136, 'high': 140, 'low': 134, 'close': 138, 'volume': 2400},
    ]
    
    analyzer = TechnicalAnalyzer()
    
    # Тест ATR
    atr = analyzer.calculate_atr(test_candles)
    print(f"\nATR: {atr}")
    
    # Тест уровней Фибоначчи
    fib_levels = analyzer.calculate_fibonacci_levels(100, 138, is_uptrend=True)
    print(f"\nУровни Фибоначчи: {fib_levels}")
    
    # Тест определения отката
    pullback = analyzer.detect_pullback(120, fib_levels, is_uptrend=True)
    print(f"\nОткат: {pullback}")
    
    # Тест адаптивных стопов
    if atr:
        stops = analyzer.calculate_adaptive_stops(138, atr, 'UP')
        print(f"\nАдаптивные стопы: {stops}")
    
    # Тест волатильности
    volatility = analyzer.calculate_volatility(test_candles)
    print(f"\nВолатильность: {volatility}%")
