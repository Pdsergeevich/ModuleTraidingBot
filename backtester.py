"""
Модуль бэктестинга на исторических данных
Позволяет протестировать стратегию без риска реальных денег
"""

import asyncio
import logging
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

from config import Config
from ai_analyzer import AIAnalyzer
from trading_engine import Position

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Класс для проведения бэктестинга"""
    
    def __init__(self, initial_capital: float = None):
        """
        Инициализация движка бэктестинга
        
        Args:
            initial_capital: Начальный капитал для тестирования
        """
        self.initial_capital = initial_capital or Config.BACKTEST_INITIAL_CAPITAL
        self.current_balance = self.initial_capital
        self.positions: List[Position] = []
        self.closed_positions: List[Position] = []
        self.historical_news = []
        self.historical_prices = {}
        self.ai_analyzer = None
        
    async def initialize(self):
        """Инициализация компонентов"""
        self.ai_analyzer = AIAnalyzer()
        logger.info("✅ Бэктестер инициализирован")
    
    def load_historical_news(self, filepath: str) -> bool:
        """
        Загрузка исторических новостей из JSON файла
        
        Args:
            filepath: Путь к файлу с новостями
            
        Returns:
            True если загрузка успешна
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.historical_news = json.load(f)
            
            # Сортируем по времени
            self.historical_news.sort(key=lambda x: x['timestamp'])
            
            logger.info(f"✅ Загружено {len(self.historical_news)} исторических новостей")
            return True
            
        except FileNotFoundError:
            logger.error(f"❌ Файл {filepath} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки новостей: {e}")
            return False
    
    def load_historical_prices(self, filepath: str) -> bool:
        """
        Загрузка исторических цен из CSV файла
        Формат CSV: timestamp,ticker,open,high,low,close,volume
        
        Args:
            filepath: Путь к файлу с ценами
            
        Returns:
            True если загрузка успешна
        """
        try:
            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Группируем по тикерам
            for ticker in df['ticker'].unique():
                ticker_data = df[df['ticker'] == ticker].sort_values('timestamp')
                self.historical_prices[ticker] = ticker_data.to_dict('records')
            
            logger.info(
                f"✅ Загружены цены для {len(self.historical_prices)} инструментов"
            )
            return True
            
        except FileNotFoundError:
            logger.error(f"❌ Файл {filepath} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки цен: {e}")
            return False
    
    def get_price_at_time(self, ticker: str, timestamp: datetime) -> Optional[float]:
        """
        Получение цены инструмента в определенный момент времени
        
        Args:
            ticker: Тикер инструмента
            timestamp: Временная метка
            
        Returns:
            Цена или None
        """
        if ticker not in self.historical_prices:
            return None
        
        prices = self.historical_prices[ticker]
        
        # Находим ближайшую цену к указанному времени
        for price_data in prices:
            if price_data['timestamp'] >= timestamp:
                return price_data['close']
        
        return None
    
    def get_price_movement(
        self,
        ticker: str,
        start_time: datetime,
        duration_seconds: int
    ) -> Dict:
        """
        Получение движения цены за определенный период
        
        Args:
            ticker: Тикер инструмента
            start_time: Время начала наблюдения
            duration_seconds: Длительность наблюдения в секундах
            
        Returns:
            Словарь с информацией о движении цены
        """
        if ticker not in self.historical_prices:
            return {'success': False, 'reason': 'no_price_data'}
        
        start_price = self.get_price_at_time(ticker, start_time)
        if not start_price:
            return {'success': False, 'reason': 'no_start_price'}
        
        end_time = start_time + timedelta(seconds=duration_seconds)
        end_price = self.get_price_at_time(ticker, end_time)
        if not end_price:
            return {'success': False, 'reason': 'no_end_price'}
        
        # Вычисляем изменение
        price_change = ((end_price - start_price) / start_price) * 100
        direction = 'UP' if price_change > 0 else 'DOWN' if price_change < 0 else 'NEUTRAL'
        
        return {
            'success': True,
            'ticker': ticker,
            'start_price': start_price,
            'end_price': end_price,
            'price_change_percent': price_change,
            'direction': direction
        }
    
    def can_open_position(self) -> bool:
        """Проверка возможности открытия позиции"""
        if len(self.positions) >= Config.MAX_OPEN_POSITIONS:
            return False
        
        if self.current_balance < Config.MIN_BALANCE:
            return False
        
        # Проверка просадки
        drawdown = ((self.initial_capital - self.current_balance) / self.initial_capital) * 100
        if drawdown > Config.MAX_DRAWDOWN_PERCENT:
            return False
        
        return True
    
    def open_position(
        self,
        ticker: str,
        direction: str,
        entry_price: float,
        entry_time: datetime
    ) -> Optional[Position]:
        """
        Открытие позиции в бэктесте
        
        Args:
            ticker: Тикер инструмента
            direction: Направление (UP/DOWN)
            entry_price: Цена входа
            entry_time: Время входа
            
        Returns:
            Объект Position или None
        """
        if not self.can_open_position():
            return None
        
        # Вычисляем размер позиции
        max_position_value = self.current_balance * (Config.MAX_POSITION_SIZE_PERCENT / 100)
        quantity = int(max_position_value / entry_price)
        
        if quantity < 1:
            return None
        
        # Вычисляем SL и TP
        if direction == 'UP':
            stop_loss = entry_price * (1 - Config.STOP_LOSS_PERCENT / 100)
            take_profit = entry_price * (1 + Config.TAKE_PROFIT_PERCENT / 100)
        else:
            stop_loss = entry_price * (1 + Config.STOP_LOSS_PERCENT / 100)
            take_profit = entry_price * (1 - Config.TAKE_PROFIT_PERCENT / 100)
        
        position = Position(
            ticker=ticker,
            figi=f'FIGI_{ticker}',  # Фиктивный FIGI для бэктеста
            direction=direction,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        position.entry_time = entry_time
        
        self.positions.append(position)
        
        logger.info(
            f"📈 [BACKTEST] Открытие позиции: {ticker} ({direction}) | "
            f"Количество: {quantity} | Цена: {entry_price:.2f}"
        )
        
        return position
    
    def update_positions(self, current_time: datetime):
        """
        Обновление открытых позиций и проверка SL/TP
        
        Args:
            current_time: Текущее время в бэктесте
        """
        for position in self.positions[:]:
            current_price = self.get_price_at_time(position.ticker, current_time)
            
            if not current_price:
                continue
            
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
            else:
                if current_price >= position.stop_loss:
                    should_close = True
                    close_reason = 'stop_loss'
                    current_price = position.stop_loss
                elif current_price <= position.take_profit:
                    should_close = True
                    close_reason = 'take_profit'
                    current_price = position.take_profit
            
            if should_close:
                self.close_position(position, current_price, current_time, close_reason)
    
    def close_position(
        self,
        position: Position,
        close_price: float,
        close_time: datetime,
        reason: str
    ):
        """
        Закрытие позиции в бэктесте
        
        Args:
            position: Объект позиции
            close_price: Цена закрытия
            close_time: Время закрытия
            reason: Причина закрытия
        """
        position.is_closed = True
        position.close_price = close_price
        position.close_time = close_time
        position.profit_loss = position.calculate_pnl(close_price)
        
        # Обновляем баланс
        self.current_balance += position.profit_loss
        
        # Переносим в историю
        self.positions.remove(position)
        self.closed_positions.append(position)
        
        logger.info(
            f"📉 [BACKTEST] Закрытие позиции: {position.ticker} | "
            f"Причина: {reason} | P/L: {position.profit_loss:+.2f} RUB | "
            f"Баланс: {self.current_balance:.2f} RUB"
        )
    
    async def run_backtest(self) -> Dict:
        """
        Запуск бэктестинга
        
        Returns:
            Словарь с результатами
        """
        logger.info("="*60)
        logger.info("🔄 ЗАПУСК БЭКТЕСТИНГА")
        logger.info(f"💰 Начальный капитал: {self.initial_capital:.2f} RUB")
        logger.info("="*60)
        
        await self.initialize()
        
        # Загружаем данные
        if not self.load_historical_news(Config.BACKTEST_NEWS_FILE):
            return {'error': 'Failed to load news'}
        
        if not self.load_historical_prices(Config.BACKTEST_PRICES_FILE):
            return {'error': 'Failed to load prices'}
        
        # Проходим по всем новостям
        for idx, news in enumerate(self.historical_news):
            news_time = datetime.fromisoformat(news['timestamp'])
            
            logger.info(f"\n--- Новость {idx+1}/{len(self.historical_news)} ---")
            logger.info(f"⏰ Время: {news_time}")
            logger.info(f"📰 Канал: {news['channel_name']}")
            logger.info(f"📝 Текст: {news['text'][:100]}...")
            
            # Анализируем новость с помощью ИИ
            analysis = await self.ai_analyzer.analyze_news(
                news['text'],
                news['channel_name']
            )
            
            if not analysis:
                logger.info("⏭️  Новость пропущена (не релевантна)")
                continue
            
            ticker = analysis['ticker']
            expected_direction = analysis['direction']
            confidence = analysis['confidence']
            
            logger.info(
                f"🎯 ИИ-анализ: {ticker} | {expected_direction} | "
                f"Уверенность: {confidence:.2%}"
            )
            
            # Проверяем движение цены
            movement = self.get_price_movement(
                ticker,
                news_time,
                Config.PRICE_CONFIRMATION_TIMEOUT
            )
            
            if not movement['success']:
                logger.info(f"⚠️  Нет данных о ценах для {ticker}")
                continue
            
            actual_direction = movement['direction']
            price_change = movement['price_change_percent']
            
            logger.info(
                f"📊 Движение цены: {actual_direction} ({price_change:+.2f}%)"
            )
            
            # Проверяем совпадение прогноза и движения
            if (expected_direction == actual_direction and 
                abs(price_change) >= Config.MIN_PRICE_MOVEMENT):
                
                logger.info("✅ Сигнал подтвержден! Открытие позиции...")
                
                position = self.open_position(
                    ticker=ticker,
                    direction=expected_direction,
                    entry_price=movement['start_price'],
                    entry_time=news_time
                )
                
                if position:
                    logger.info(
                        f"✅ Позиция #{len(self.closed_positions) + len(self.positions)} открыта"
                    )
            else:
                logger.info("❌ Сигнал не подтвержден")
            
            # Обновляем открытые позиции
            self.update_positions(news_time + timedelta(seconds=Config.PRICE_CONFIRMATION_TIMEOUT))
        
        # Закрываем все оставшиеся позиции
        logger.info("\n" + "="*60)
        logger.info("🏁 ЗАВЕРШЕНИЕ БЭКТЕСТИНГА")
        
        if self.positions:
            logger.info(f"Закрытие {len(self.positions)} оставшихся позиций...")
            for position in self.positions[:]:
                last_time = datetime.fromisoformat(self.historical_news[-1]['timestamp'])
                last_price = self.get_price_at_time(position.ticker, last_time)
                if last_price:
                    self.close_position(position, last_price, last_time, 'backtest_end')
        
        # Вычисляем статистику
        stats = self.get_statistics()
        
        logger.info("="*60)
        logger.info("📊 РЕЗУЛЬТАТЫ БЭКТЕСТИНГА")
        logger.info("="*60)
        logger.info(f"💰 Начальный капитал: {stats['initial_capital']:.2f} RUB")
        logger.info(f"💰 Конечный капитал:  {stats['final_capital']:.2f} RUB")
        logger.info(f"📈 Общая прибыль:     {stats['total_pnl']:+.2f} RUB ({stats['total_return']:+.2f}%)")
        logger.info(f"📊 Всего сделок:      {stats['total_trades']}")
        logger.info(f"✅ Прибыльных:        {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
        logger.info(f"❌ Убыточных:         {stats['losing_trades']}")
        logger.info(f"💵 Средняя прибыль:   {stats['avg_pnl']:+.2f} RUB")
        logger.info(f"📉 Макс. просадка:    {stats['max_drawdown']:.2f}%")
        logger.info("="*60)
        
        return stats
    
    def get_statistics(self) -> Dict:
        """Получение статистики бэктеста"""
        total_trades = len(self.closed_positions)
        
        if total_trades == 0:
            return {
                'initial_capital': self.initial_capital,
                'final_capital': self.current_balance,
                'total_pnl': 0.0,
                'total_return': 0.0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'max_drawdown': 0.0
            }
        
        winning_trades = sum(1 for p in self.closed_positions if p.profit_loss > 0)
        total_pnl = sum(p.profit_loss for p in self.closed_positions)
        
        # Вычисляем максимальную просадку
        max_drawdown = 0.0
        peak_balance = self.initial_capital
        
        for position in self.closed_positions:
            balance_after = self.initial_capital + sum(
                p.profit_loss for p in self.closed_positions 
                if p.close_time <= position.close_time
            )
            
            if balance_after > peak_balance:
                peak_balance = balance_after
            
            drawdown = ((peak_balance - balance_after) / peak_balance) * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            'initial_capital': self.initial_capital,
            'final_capital': self.current_balance,
            'total_pnl': total_pnl,
            'total_return': (total_pnl / self.initial_capital) * 100,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': total_trades - winning_trades,
            'win_rate': (winning_trades / total_trades) * 100,
            'avg_pnl': total_pnl / total_trades,
            'max_drawdown': max_drawdown
        }
    
    def export_results(self, output_file: str = 'backtest_results.json'):
        """
        Экспорт результатов в JSON файл
        
        Args:
            output_file: Путь к выходному файлу
        """
        results = {
            'statistics': self.get_statistics(),
            'trades': [p.to_dict() for p in self.closed_positions]
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Результаты экспортированы в {output_file}")


if __name__ == '__main__':
    # Запуск бэктестинга
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        backtester = BacktestEngine()
        results = await backtester.run_backtest()
        
        if 'error' not in results:
            backtester.export_results()
    
    asyncio.run(main())
