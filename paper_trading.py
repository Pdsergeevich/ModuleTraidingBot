"""
Модуль Paper Trading (демо-торговля)
Симуляция торговли без реальных сделок, но с реальными ценами
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal

from config import Config
from trading_engine import Position
from technical_analysis import TechnicalAnalyzer

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """Класс для симуляции торговли без реальных сделок"""
    
    def __init__(self, initial_capital: float = 100000):
        """
        Инициализация Paper Trading движка
        
        Args:
            initial_capital: Начальный виртуальный капитал
        """
        self.initial_capital = initial_capital
        self.current_balance = initial_capital
        self.available_balance = initial_capital  # Свободные средства
        self.technical_analyzer = TechnicalAnalyzer()
        
        self.positions: List[Position] = []
        self.closed_positions: List[Position] = []
        
        # Счетчики для логирования
        self.trade_counter = 0
        
        logger.info("="*70)
        logger.info("📝 PAPER TRADING РЕЖИМ АКТИВИРОВАН")
        logger.info("⚠️  ВСЕ СДЕЛКИ СИМУЛИРУЮТСЯ - РЕАЛЬНЫЕ ТОРГИ НЕ ПРОИСХОДЯТ")
        logger.info(f"💰 Виртуальный стартовый капитал: {self.initial_capital:.2f} RUB")
        logger.info("="*70)
    
    def can_open_position(self) -> bool:
        """
        Проверка возможности открытия новой позиции
        
        Returns:
            True если можно открыть позицию
        """
        # Проверяем количество открытых позиций
        if len(self.positions) >= Config.MAX_OPEN_POSITIONS:
            logger.warning(
                f"⚠️ [DEMO] Достигнут лимит открытых позиций ({Config.MAX_OPEN_POSITIONS})"
            )
            return False
        
        # Проверяем минимальный баланс
        if self.available_balance < Config.MIN_BALANCE:
            logger.warning(
                f"⚠️ [DEMO] Недостаточный баланс: {self.available_balance:.2f} RUB"
            )
            return False
        
        # Проверяем максимальную просадку
        if self.initial_capital > 0:
            drawdown = ((self.initial_capital - self.current_balance) / self.initial_capital) * 100
            if drawdown > Config.MAX_DRAWDOWN_PERCENT:
                logger.warning(
                    f"⚠️ [DEMO] Превышена максимальная просадка: {drawdown:.2f}%"
                )
                return False
        
        return True
    
    async def open_pullback_position(
        self,
        ticker: str,
        figi: str,
        direction: str,
        entry_price: float,
        atr: float,
        lot_size: int = 1
    ) -> Optional[Position]:
        """
        Симуляция открытия позиции по стратегии откатов
        
        Args:
            ticker: Тикер инструмента
            figi: FIGI инструмента
            direction: Направление (UP/DOWN)
            entry_price: Цена входа
            atr: Значение ATR
            lot_size: Размер лота
            
        Returns:
            Объект Position или None
        """
        if not self.can_open_position():
            return None
        
        # Рассчитываем адаптивные стопы
        stops = self.technical_analyzer.calculate_adaptive_stops(
            entry_price,
            atr,
            direction
        )
        
        # Проверяем Risk/Reward
        if stops['risk_reward_ratio'] < Config.MIN_RISK_REWARD_RATIO:
            logger.warning(
                f"⚠️ [DEMO] Risk/Reward слишком низкий: "
                f"1:{stops['risk_reward_ratio']:.2f}"
            )
            return None
        
        # Вычисляем количество лотов
        max_position_value = self.available_balance * (Config.MAX_POSITION_SIZE_PERCENT / 100)
        max_lots = int(max_position_value / (entry_price * lot_size))
        
        if max_lots < 1:
            logger.warning("⚠️ [DEMO] Недостаточно средств для открытия позиции")
            return None
        
        # Вычисляем стоимость позиции
        position_cost = max_lots * lot_size * entry_price
        
        self.trade_counter += 1
        
        # Создаем виртуальную позицию
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
        position.order_id = f"DEMO_{self.trade_counter}"
        
        # Резервируем средства
        self.available_balance -= position_cost
        
        self.positions.append(position)
        
        # Красивый лог открытия позиции
        logger.info("\n" + "🟢 " + "="*66)
        logger.info(f"📈 [DEMO] ОТКРЫТИЕ ПОЗИЦИИ #{self.trade_counter}")
        logger.info("="*70)
        logger.info(f"   🎯 Инструмент:        {ticker}")
        logger.info(f"   📊 Стратегия:         ОТКАТЫ (Pullback)")
        logger.info(f"   ↗️  Направление:       {direction} ({'LONG' if direction == 'UP' else 'SHORT'})")
        logger.info(f"   🔢 Количество:        {position.quantity} шт. ({max_lots} лотов)")
        logger.info(f"   💵 Цена входа:        {entry_price:.2f} RUB")
        logger.info(f"   💰 Стоимость позиции: {position_cost:.2f} RUB")
        logger.info(f"   🛡️  Stop-Loss:         {stops['stop_loss']:.2f} RUB (-{stops['stop_percent']:.2f}%)")
        logger.info(f"   🎯 Take-Profit:       {stops['take_profit']:.2f} RUB (+{stops['take_percent']:.2f}%)")
        logger.info(f"   📊 ATR:               {atr:.4f}")
        logger.info(f"   ⚖️  Risk/Reward:       1:{stops['risk_reward_ratio']:.2f}")
        logger.info(f"   ⏰ Время:             {position.entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("─"*70)
        logger.info(f"   💼 Свободно средств:  {self.available_balance:.2f} RUB")
        logger.info(f"   💰 Общий капитал:     {self.current_balance:.2f} RUB")
        logger.info(f"   📊 Открытых позиций:  {len(self.positions)}")
        logger.info("="*70 + "\n")
        
        return position
    
    async def open_range_trading_position(
        self,
        ticker: str,
        figi: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        lot_size: int = 1
    ) -> Optional[Position]:
        """
        Симуляция открытия позиции по стратегии Range Trading
        
        Args:
            ticker: Тикер
            figi: FIGI
            direction: Направление
            entry_price: Цена входа
            stop_loss: Stop-loss
            take_profit: Take-profit
            lot_size: Размер лота
            
        Returns:
            Объект Position или None
        """
        if not self.can_open_position():
            return None
        
        # Проверяем Risk/Reward
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        risk_reward = reward / risk if risk > 0 else 0
        
        if risk_reward < Config.MIN_RISK_REWARD_RATIO:
            logger.warning(
                f"⚠️ [DEMO] Risk/Reward для Range Trading слишком низкий: "
                f"1:{risk_reward:.2f}"
            )
            return None
        
        # Вычисляем количество лотов
        max_position_value = self.available_balance * (Config.MAX_POSITION_SIZE_PERCENT / 100)
        max_lots = int(max_position_value / (entry_price * lot_size))
        
        if max_lots < 1:
            logger.warning("⚠️ [DEMO] Недостаточно средств")
            return None
        
        position_cost = max_lots * lot_size * entry_price
        
        self.trade_counter += 1
        
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
        position.order_id = f"DEMO_{self.trade_counter}"
        
        self.available_balance -= position_cost
        self.positions.append(position)
        
        # Лог открытия Range Trading позиции
        logger.info("\n" + "🟢 " + "="*66)
        logger.info(f"📊 [DEMO] ОТКРЫТИЕ ПОЗИЦИИ #{self.trade_counter}")
        logger.info("="*70)
        logger.info(f"   🎯 Инструмент:        {ticker}")
        logger.info(f"   📊 Стратегия:         RANGE TRADING")
        logger.info(f"   ↗️  Направление:       {direction}")
        logger.info(f"   🔢 Количество:        {position.quantity} шт. ({max_lots} лотов)")
        logger.info(f"   💵 Цена входа:        {entry_price:.2f} RUB")
        logger.info(f"   💰 Стоимость позиции: {position_cost:.2f} RUB")
        logger.info(f"   🛡️  Stop-Loss:         {stop_loss:.2f} RUB")
        logger.info(f"   🎯 Take-Profit:       {take_profit:.2f} RUB")
        logger.info(f"   ⚖️  Risk/Reward:       1:{risk_reward:.2f}")
        logger.info(f"   ⏰ Время:             {position.entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("─"*70)
        logger.info(f"   💼 Свободно средств:  {self.available_balance:.2f} RUB")
        logger.info(f"   💰 Общий капитал:     {self.current_balance:.2f} RUB")
        logger.info(f"   📊 Открытых позиций:  {len(self.positions)}")
        logger.info("="*70 + "\n")
        
        return position
    
    async def close_position(
        self,
        position: Position,
        current_price: float,
        reason: str = 'manual'
    ):
        """
        Симуляция закрытия позиции
        
        Args:
            position: Позиция для закрытия
            current_price: Текущая цена
            reason: Причина закрытия
        """
        # Обновляем информацию о позиции
        position.is_closed = True
        position.close_price = current_price
        position.close_time = datetime.now()
        position.close_reason = reason
        position.profit_loss = position.calculate_pnl(current_price)
        
        # Возвращаем средства и добавляем прибыль/убыток
        position_value = position.quantity * current_price
        self.available_balance += position_value
        self.current_balance += position.profit_loss
        
        # Переносим в историю
        self.positions.remove(position)
        self.closed_positions.append(position)
        
        # Определяем цвет для лога
        is_profit = position.profit_loss > 0
        emoji = "💚" if is_profit else "💔"
        color = "🟢" if is_profit else "🔴"
        
        hold_time_seconds = (position.close_time - position.entry_time).seconds
        hold_minutes = hold_time_seconds // 60
        hold_seconds = hold_time_seconds % 60
        
        profit_percent = (position.profit_loss / (position.entry_price * position.quantity)) * 100
        
        # Красивый лог закрытия
        logger.info("\n" + color + " " + "="*66)
        logger.info(f"{emoji} [DEMO] ЗАКРЫТИЕ ПОЗИЦИИ #{position.order_id}")
        logger.info("="*70)
        logger.info(f"   🎯 Инструмент:        {position.ticker}")
        logger.info(f"   📊 Стратегия:         {position.strategy.upper()}")
        logger.info(f"   ↗️  Направление:       {position.direction}")
        logger.info(f"   🔢 Количество:        {position.quantity} шт.")
        logger.info(f"   💵 Цена входа:        {position.entry_price:.2f} RUB")
        logger.info(f"   💵 Цена выхода:       {current_price:.2f} RUB")
        logger.info(f"   🛑 Причина закрытия:  {reason.upper()}")
        logger.info(f"   ⏱️  Время удержания:   {hold_minutes}м {hold_seconds}с")
        logger.info("─"*70)
        logger.info(f"   {emoji} ПРИБЫЛЬ/УБЫТОК:    {position.profit_loss:+.2f} RUB ({profit_percent:+.2f}%)")
        logger.info(f"   📊 Макс. прибыль:     {position.max_profit:+.2f} RUB")
        logger.info(f"   📉 Макс. убыток:      {position.max_loss:+.2f} RUB")
        logger.info("─"*70)
        logger.info(f"   💼 Свободно средств:  {self.available_balance:.2f} RUB")
        logger.info(f"   💰 Общий капитал:     {self.current_balance:.2f} RUB")
        logger.info(f"   📈 Доходность:        {((self.current_balance - self.initial_capital) / self.initial_capital * 100):+.2f}%")
        logger.info(f"   📊 Открытых позиций:  {len(self.positions)}")
        logger.info(f"   ✅ Закрытых позиций:  {len(self.closed_positions)}")
        logger.info("="*70 + "\n")
    
    async def monitor_positions(self, get_price_func):
        """
        Мониторинг открытых позиций для срабатывания SL/TP
        
        Args:
            get_price_func: Асинхронная функция для получения текущей цены
        """
        logger.info("👀 [DEMO] Запуск мониторинга виртуальных позиций...")
        
        while True:
            try:
                for position in self.positions[:]:
                    # Получаем текущую цену через переданную функцию
                    current_price_decimal = await get_price_func(position.figi)
                    
                    if not current_price_decimal:
                        continue
                    
                    current_price = float(current_price_decimal)
                    
                    # Обновляем P/L
                    position.calculate_pnl(current_price)
                    
                    # Проверяем условия закрытия
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
                logger.info("🛑 [DEMO] Мониторинг позиций остановлен")
                break
            except Exception as e:
                logger.error(f"❌ [DEMO] Ошибка в мониторинге позиций: {e}")
                await asyncio.sleep(5)
    
    def get_statistics(self) -> Dict:
        """Получение статистики торговли"""
        total_trades = len(self.closed_positions)
        
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'initial_capital': self.initial_capital,
                'current_balance': self.current_balance,
                'total_return': 0.0,
                'avg_hold_time': 0,
                'pullback_trades': 0,
                'range_trades': 0,
                'max_profit_trade': 0.0,
                'max_loss_trade': 0.0
            }
        
        winning_trades = sum(1 for p in self.closed_positions if p.profit_loss > 0)
        total_pnl = sum(p.profit_loss for p in self.closed_positions)
        avg_hold_time = sum(
            (p.close_time - p.entry_time).seconds 
            for p in self.closed_positions
        ) / total_trades
        
        pullback_trades = sum(1 for p in self.closed_positions if p.strategy == 'pullback')
        range_trades = sum(1 for p in self.closed_positions if p.strategy == 'range_trading')
        
        max_profit_trade = max((p.profit_loss for p in self.closed_positions), default=0.0)
        max_loss_trade = min((p.profit_loss for p in self.closed_positions), default=0.0)
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': total_trades - winning_trades,
            'win_rate': (winning_trades / total_trades) * 100,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / total_trades,
            'initial_capital': self.initial_capital,
            'current_balance': self.current_balance,
            'total_return': ((self.current_balance - self.initial_capital) / self.initial_capital) * 100,
            'avg_hold_time': int(avg_hold_time),
            'pullback_trades': pullback_trades,
            'range_trades': range_trades,
            'max_profit_trade': max_profit_trade,
            'max_loss_trade': max_loss_trade
        }
    
    def print_summary(self):
        """Вывод итоговой статистики"""
        stats = self.get_statistics()
        
        logger.info("\n" + "="*70)
        logger.info("📊 [DEMO] ИТОГОВАЯ СТАТИСТИКА PAPER TRADING")
        logger.info("="*70)
        logger.info(f"💰 Начальный капитал:      {stats['initial_capital']:.2f} RUB")
        logger.info(f"💰 Конечный капитал:       {stats['current_balance']:.2f} RUB")
        logger.info(f"📈 Прибыль/Убыток:         {stats['total_pnl']:+.2f} RUB")
        logger.info(f"📊 Доходность:             {stats['total_return']:+.2f}%")
        logger.info("─"*70)
        logger.info(f"📊 Всего сделок:           {stats['total_trades']}")
        logger.info(f"✅ Прибыльных:             {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
        logger.info(f"❌ Убыточных:              {stats['losing_trades']}")
        logger.info(f"💵 Средняя прибыль:        {stats['avg_pnl']:+.2f} RUB")
        logger.info(f"⏱️  Среднее время сделки:   {stats['avg_hold_time']}с")
        logger.info("─"*70)
        logger.info(f"📈 Сделок по откатам:      {stats['pullback_trades']}")
        logger.info(f"📊 Range Trading сделок:   {stats['range_trades']}")
        logger.info(f"💚 Лучшая сделка:          +{stats['max_profit_trade']:.2f} RUB")
        logger.info(f"💔 Худшая сделка:          {stats['max_loss_trade']:.2f} RUB")
        logger.info("="*70 + "\n")


if __name__ == '__main__':
    # Тестирование Paper Trading движка
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        engine = PaperTradingEngine(initial_capital=100000)
        
        # Симуляция открытия позиции
        position = await engine.open_pullback_position(
            ticker='SBER',
            figi='BBG004730N88',
            direction='UP',
            entry_price=250.50,
            atr=5.2,
            lot_size=10
        )
        
        if position:
            # Симуляция закрытия с прибылью
            await asyncio.sleep(1)
            await engine.close_position(position, 255.00, 'take_profit')
        
        # Вывод статистики
        engine.print_summary()
    
    asyncio.run(test())
