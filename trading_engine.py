"""
Модуль торговой логики
Стратегия с откатами, адаптивными стопами и Range Trading
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal

from tinkoff.invest import (
    AsyncClient,
    OrderDirection,
    OrderType,
)
from tinkoff.invest.utils import quotation_to_decimal

from config import Config
from technical_analysis import TechnicalAnalyzer

logger = logging.getLogger(__name__)


class Position:
    """Класс для хранения информации о позиции"""
    
    def __init__(self, ticker: str, figi: str, direction: str, 
                 quantity: int, entry_price: float, stop_loss: float, 
                 take_profit: float, strategy: str = 'pullback', atr: float = 0):
        self.ticker = ticker
        self.figi = figi
        self.direction = direction  # UP (long) / DOWN (short)
        self.quantity = quantity
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.strategy = strategy  # 'pullback' или 'range_trading'
        self.atr = atr  # ATR на момент входа
        self.entry_time = datetime.now()
        self.order_id = None
        self.is_closed = False
        self.close_price = None
        self.close_time = None
        self.profit_loss = 0.0
        self.close_reason = None
        
        # Дополнительная информация
        self.max_profit = 0.0
        self.max_loss = 0.0
    
    def calculate_pnl(self, current_price: float) -> float:
        """Расчет текущей прибыли/убытка"""
        if self.direction == 'UP':
            pnl = (current_price - self.entry_price) * self.quantity
        else:
            pnl = (self.entry_price - current_price) * self.quantity
        
        # Обновляем максимальные значения
        if pnl > self.max_profit:
            self.max_profit = pnl
        if pnl < self.max_loss:
            self.max_loss = pnl
        
        return pnl
    
    def to_dict(self) -> Dict:
        """Преобразование в словарь"""
        return {
            'ticker': self.ticker,
            'figi': self.figi,
            'direction': self.direction,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'strategy': self.strategy,
            'atr': self.atr,
            'entry_time': self.entry_time.isoformat(),
            'is_closed': self.is_closed,
            'close_price': self.close_price,
            'close_time': self.close_time.isoformat() if self.close_time else None,
            'close_reason': self.close_reason,
            'profit_loss': self.profit_loss,
            'max_profit': self.max_profit,
            'max_loss': self.max_loss,
            'hold_time_seconds': (self.close_time - self.entry_time).seconds if self.close_time else 0
        }


class TradingEngine:
    """Класс для управления торговыми операциями"""
    
    def __init__(self, account_id: str, is_sandbox: bool = True):
        """
        Инициализация торгового движка
        
        Args:
            account_id: ID торгового счета
            is_sandbox: True - песочница, False - боевой режим
        """
        self.token = Config.TINKOFF_TOKEN
        self.account_id = account_id
        self.is_sandbox = is_sandbox
        self.client = None
        self.technical_analyzer = TechnicalAnalyzer()
        self.positions: List[Position] = []
        self.closed_positions: List[Position] = []
        self.initial_balance = 0.0
        self.current_balance = 0.0
        
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
        
        # Получаем текущий баланс
        await self._update_balance()
        
        logger.info(
            f"✅ Торговый движок подключен ({'песочница' if self.is_sandbox else 'боевой'})"
        )
        logger.info(f"💰 Текущий баланс: {self.current_balance:.2f} RUB")
    
    async def disconnect(self):
        """Отключение от API"""
        if self.client:
            await self.client.close()
            logger.info("✅ Торговый движок отключен")
    
    async def _update_balance(self):
        """Обновление информации о балансе"""
        try:
            portfolio = await self.client.operations.get_portfolio(
                account_id=self.account_id
            )
            
            # Суммируем балансы
            total_balance = 0.0
            for position in portfolio.positions:
                if position.instrument_type == 'currency':
                    balance = quotation_to_decimal(position.quantity)
                    total_balance += float(balance)
            
            self.current_balance = total_balance
            
            if self.initial_balance == 0:
                self.initial_balance = total_balance
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления баланса: {e}")
    
    def can_open_position(self) -> bool:
        """
        Проверка возможности открытия новой позиции
        
        Returns:
            True если можно открыть позицию
        """
        # Проверяем количество открытых позиций
        if len(self.positions) >= Config.MAX_OPEN_POSITIONS:
            logger.warning(f"⚠️ Достигнут лимит открытых позиций ({Config.MAX_OPEN_POSITIONS})")
            return False
        
        # Проверяем минимальный баланс
        if self.current_balance < Config.MIN_BALANCE:
            logger.warning(f"⚠️ Недостаточный баланс: {self.current_balance:.2f} RUB")
            return False
        
        # Проверяем максимальную просадку
        if self.initial_balance > 0:
            drawdown = ((self.initial_balance - self.current_balance) / self.initial_balance) * 100
            if drawdown > Config.MAX_DRAWDOWN_PERCENT:
                logger.warning(f"⚠️ Превышена максимальная просадка: {drawdown:.2f}%")
                return False
        
        return True
    
    async def open_pullback_position(
        self,
        ticker: str,
        figi: str,
        direction: str,
        entry_price: float,
        atr: float,
        lot_size: int
    ) -> Optional[Position]:
        """
        Открытие позиции по стратегии откатов с адаптивными стопами
        
        Args:
            ticker: Тикер инструмента
            figi: FIGI инструмента
            direction: Направление (UP для long, DOWN для short)
            entry_price: Цена входа
            atr: Значение ATR для расчета стопов
            lot_size: Размер лота
            
        Returns:
            Объект Position или None при ошибке
        """
        if not self.can_open_position():
            return None
        
        try:
            # Вычисляем адаптивные стопы на основе ATR
            stops = self.technical_analyzer.calculate_adaptive_stops(
                entry_price,
                atr,
                direction
            )
            
            # Проверяем Risk/Reward соотношение
            if stops['risk_reward_ratio'] < Config.MIN_RISK_REWARD_RATIO:
                logger.warning(
                    f"⚠️ Risk/Reward соотношение слишком низкое: "
                    f"1:{stops['risk_reward_ratio']:.2f} "
                    f"(минимум: 1:{Config.MIN_RISK_REWARD_RATIO})"
                )
                return None
            
            # Вычисляем количество лотов
            max_position_value = self.current_balance * (Config.MAX_POSITION_SIZE_PERCENT / 100)
            max_lots = int(max_position_value / (entry_price * lot_size))
            
            if max_lots < 1:
                logger.warning("⚠️ Недостаточно средств для открытия позиции")
                return None
            
            # Определяем направление ордера
            order_direction = (
                OrderDirection.ORDER_DIRECTION_BUY 
                if direction == 'UP' 
                else OrderDirection.ORDER_DIRECTION_SELL
            )
            
            # Выставляем рыночный ордер
            logger.info(
                f"📈 Открытие позиции {ticker} ({direction}) по стратегии ОТКАТОВ:\n"
                f"   Лоты: {max_lots}\n"
                f"   Цена входа: ~{entry_price:.2f}\n"
                f"   Stop-Loss: {stops['stop_loss']:.2f} (-{stops['stop_percent']:.2f}%)\n"
                f"   Take-Profit: {stops['take_profit']:.2f} (+{stops['take_percent']:.2f}%)\n"
                f"   Risk/Reward: 1:{stops['risk_reward_ratio']:.2f}\n"
                f"   ATR: {atr:.4f}"
            )
            
            order_response = await self.client.orders.post_order(
                figi=figi,
                quantity=max_lots,
                direction=order_direction,
                account_id=self.account_id,
                order_type=OrderType.ORDER_TYPE_MARKET
            )
            
            # Создаем объект позиции
            position = Position(
                ticker=ticker,
                figi=figi,
                direction=direction,
                quantity=max_lots * lot_size,
                entry_price=entry_price,
                stop_loss=stops['stop_loss'],
                take_profit=stops['take_profit'],
                strategy='pullback',
                atr=atr
            )
            position.order_id = order_response.order_id
            
            self.positions.append(position)
            
            logger.info(f"✅ Позиция #{len(self.positions)} успешно открыта")
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Ошибка открытия позиции: {e}")
            return None
    
    async def open_range_trading_position(
        self,
        ticker: str,
        figi: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        lot_size: int
    ) -> Optional[Position]:
        """
        Открытие позиции по стратегии Range Trading (нейтральный контекст)
        
        Args:
            ticker: Тикер инструмента
            figi: FIGI инструмента
            direction: Направление (UP/DOWN)
            entry_price: Цена входа
            stop_loss: Уровень stop-loss
            take_profit: Уровень take-profit
            lot_size: Размер лота
            
        Returns:
            Объект Position или None
        """
        if not self.can_open_position():
            return None
        
        try:
            # Вычисляем количество лотов
            max_position_value = self.current_balance * (Config.MAX_POSITION_SIZE_PERCENT / 100)
            max_lots = int(max_position_value / (entry_price * lot_size))
            
            if max_lots < 1:
                logger.warning("⚠️ Недостаточно средств для открытия позиции")
                return None
            
            # Проверяем Risk/Reward
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            risk_reward = reward / risk if risk > 0 else 0
            
            if risk_reward < Config.MIN_RISK_REWARD_RATIO:
                logger.warning(
                    f"⚠️ Risk/Reward для Range Trading слишком низкий: 1:{risk_reward:.2f}"
                )
                return None
            
            order_direction = (
                OrderDirection.ORDER_DIRECTION_BUY 
                if direction == 'UP' 
                else OrderDirection.ORDER_DIRECTION_SELL
            )
            
            logger.info(
                f"📊 Открытие позиции {ticker} ({direction}) по стратегии RANGE TRADING:\n"
                f"   Лоты: {max_lots}\n"
                f"   Цена входа: ~{entry_price:.2f}\n"
                f"   Stop-Loss: {stop_loss:.2f}\n"
                f"   Take-Profit: {take_profit:.2f}\n"
                f"   Risk/Reward: 1:{risk_reward:.2f}"
            )
            
            order_response = await self.client.orders.post_order(
                figi=figi,
                quantity=max_lots,
                direction=order_direction,
                account_id=self.account_id,
                order_type=OrderType.ORDER_TYPE_MARKET
            )
            
            position = Position(
                ticker=ticker,
                figi=figi,
                direction=direction,
                quantity=max_lots * lot_size,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy='range_trading',
                atr=0
            )
            position.order_id = order_response.order_id
            
            self.positions.append(position)
            
            logger.info(f"✅ Range Trading позиция #{len(self.positions)} открыта")
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Ошибка открытия Range Trading позиции: {e}")
            return None
    
    async def close_position(self, position: Position, current_price: float, reason: str = 'manual'):
        """
        Закрытие позиции
        
        Args:
            position: Объект позиции
            current_price: Текущая цена
            reason: Причина закрытия (stop_loss, take_profit, manual, bot_shutdown)
        """
        try:
            # Определяем направление закрывающего ордера
            close_direction = (
                OrderDirection.ORDER_DIRECTION_SELL 
                if position.direction == 'UP' 
                else OrderDirection.ORDER_DIRECTION_BUY
            )
            
            logger.info(
                f"📉 Закрытие позиции {position.ticker} "
                f"(стратегия: {position.strategy}, причина: {reason})"
            )
            
            await self.client.orders.post_order(
                figi=position.figi,
                quantity=position.quantity,
                direction=close_direction,
                account_id=self.account_id,
                order_type=OrderType.ORDER_TYPE_MARKET
            )
            
            # Обновляем информацию о позиции
            position.is_closed = True
            position.close_price = current_price
            position.close_time = datetime.now()
            position.close_reason = reason
            position.profit_loss = position.calculate_pnl(current_price)
            
            # Переносим в историю
            self.positions.remove(position)
            self.closed_positions.append(position)
            
            # Обновляем баланс
            await self._update_balance()
            
            # Определяем эмодзи для результата
            emoji = "💚" if position.profit_loss > 0 else "💔"
            
            hold_time = (position.close_time - position.entry_time).seconds
            
            logger.info(
                f"{emoji} Позиция закрыта: {position.ticker}\n"
                f"   Стратегия: {position.strategy}\n"
                f"   Причина: {reason}\n"
                f"   Время удержания: {hold_time}с\n"
                f"   P/L: {position.profit_loss:+.2f} RUB\n"
                f"   Баланс: {self.current_balance:.2f} RUB"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия позиции: {e}")
    
    async def monitor_positions(self):
        """Мониторинг открытых позиций для срабатывания SL/TP"""
        logger.info("👀 Запуск мониторинга открытых позиций...")
        
        while True:
            try:
                for position in self.positions[:]:
                    # Получаем текущую цену
                    response = await self.client.market_data.get_last_prices(
                        figi=[position.figi]
                    )
                    
                    if not response.last_prices:
                        continue
                    
                    current_price = float(quotation_to_decimal(response.last_prices[0].price))
                    
                    # Обновляем максимальные прибыль/убыток
                    position.calculate_pnl(current_price)
                    
                    # Проверяем stop-loss
                    should_close = False
                    close_reason = None
                    
                    if position.direction == 'UP':
                        if current_price <= position.stop_loss:
                            should_close = True
                            close_reason = 'stop_loss'
                            current_price = position.stop_loss
                        elif current_price >= position.take_profit:
                            should_close = True
                            close_reason = 'take_profit'
                            current_price = position.take_profit
                    else:  # DOWN
                        if current_price >= position.stop_loss:
                            should_close = True
                            close_reason = 'stop_loss'
                            current_price = position.stop_loss
                        elif current_price <= position.take_profit:
                            should_close = True
                            close_reason = 'take_profit'
                            current_price = position.take_profit
                    
                    if should_close:
                        await self.close_position(position, current_price, close_reason)
                
                await asyncio.sleep(Config.UPDATE_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("🛑 Мониторинг позиций остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге позиций: {e}")
                await asyncio.sleep(5)
    
    def get_statistics(self) -> Dict:
        """
        Получение статистики торговли
        
        Returns:
            Словарь со статистикой
        """
        total_trades = len(self.closed_positions)
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'initial_balance': self.initial_balance,
                'current_balance': self.current_balance,
                'total_return': 0.0,
                'avg_hold_time': 0,
                'pullback_trades': 0,
                'range_trades': 0
            }
        
        winning_trades = sum(1 for p in self.closed_positions if p.profit_loss > 0)
        total_pnl = sum(p.profit_loss for p in self.closed_positions)
        avg_hold_time = sum(
            (p.close_time - p.entry_time).seconds 
            for p in self.closed_positions
        ) / total_trades
        
        # Статистика по стратегиям
        pullback_trades = sum(1 for p in self.closed_positions if p.strategy == 'pullback')
        range_trades = sum(1 for p in self.closed_positions if p.strategy == 'range_trading')
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': total_trades - winning_trades,
            'win_rate': (winning_trades / total_trades) * 100,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / total_trades,
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'total_return': ((self.current_balance - self.initial_balance) / self.initial_balance) * 100 if self.initial_balance > 0 else 0,
            'avg_hold_time': int(avg_hold_time),
            'pullback_trades': pullback_trades,
            'range_trades': range_trades
        }


if __name__ == '__main__':
    # Тестирование торгового движка
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        async with TradingEngine(Config.TINKOFF_ACCOUNT_ID, is_sandbox=True) as engine:
            if engine.can_open_position():
                print("✅ Можно открыть позицию")
            
            stats = engine.get_statistics()
            print(f"Статистика: {stats}")
    
    asyncio.run(test())
