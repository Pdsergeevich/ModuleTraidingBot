"""
Продвинутый бэктестер с ручным управлением и визуализацией
Позволяет тестировать стратегию без ИИ с полным контролем
"""

import asyncio
import logging
import json
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

from config import Config
from technical_analysis import TechnicalAnalyzer
from trading_engine import Position

logger = logging.getLogger(__name__)


class ManualBacktester:
    """Бэктестер с ручным заданием торговых сигналов"""
    
    def __init__(self, initial_capital: float = 100000):
        """
        Инициализация бэктестера
        
        Args:
            initial_capital: Начальный капитал
        """
        self.initial_capital = initial_capital
        self.current_balance = initial_capital
        self.available_balance = initial_capital
        
        self.technical_analyzer = TechnicalAnalyzer()
        
        self.positions: List[Position] = []
        self.closed_positions: List[Position] = []
        
        # Данные для визуализации
        self.trades_history = []
        self.equity_curve = []
        
        # Параметры торговой сессии
        self.session_start = dt_time(10, 0)  # 10:00
        self.session_end = dt_time(23, 30)   # 23:30
        self.close_before_end = dt_time(23, 0)  # Закрывать позиции до 23:00
        
        logger.info("="*70)
        logger.info("📊 РУЧНОЙ БЭКТЕСТЕР ИНИЦИАЛИЗИРОВАН")
        logger.info(f"💰 Начальный капитал: {self.initial_capital:.2f} RUB")
        logger.info(f"⏰ Торговая сессия: {self.session_start} - {self.session_end}")
        logger.info(f"🌙 Закрытие позиций до: {self.close_before_end}")
        logger.info("="*70)
    
    def load_candles(self, file_path: str) -> pd.DataFrame:
        """
        Загрузка свечей из CSV файла
        
        Args:
            file_path: Путь к CSV файлу
            
        Returns:
            DataFrame со свечами
        """
        logger.info(f"📂 Загрузка данных из {file_path}...")
        
        try:
            df = pd.read_csv(file_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            logger.info(f"✅ Загружено {len(df)} свечей")
            logger.info(f"   Период: {df.iloc[0]['timestamp']} - {df.iloc[-1]['timestamp']}")
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных: {e}")
            return pd.DataFrame()
    
    def is_trading_hours(self, timestamp: datetime) -> bool:
        """
        Проверка торгового времени
        
        Args:
            timestamp: Временная метка
            
        Returns:
            True если торговое время
        """
        current_time = timestamp.time()
        return self.session_start <= current_time <= self.session_end
    
    def should_close_positions(self, timestamp: datetime) -> bool:
        """
        Проверка необходимости закрытия позиций (перед концом сессии)
        
        Args:
            timestamp: Временная метка
            
        Returns:
            True если нужно закрывать позиции
        """
        return timestamp.time() >= self.close_before_end
    
    async def run_manual_backtest(
        self,
        candles_df: pd.DataFrame,
        signals: List[Dict],
        ticker: str = "TEST"
    ) -> Dict:
        """
        Запуск бэктеста с ручными сигналами
        
        Args:
            candles_df: DataFrame со свечами
            signals: Список торговых сигналов
            ticker: Тикер инструмента
            
        Returns:
            Словарь с результатами
        """
        logger.info("\n" + "="*70)
        logger.info("🚀 ЗАПУСК РУЧНОГО БЭКТЕСТИНГА")
        logger.info("="*70)
        logger.info(f"📊 Инструмент: {ticker}")
        logger.info(f"📅 Свечей: {len(candles_df)}")
        logger.info(f"📍 Сигналов: {len(signals)}")
        logger.info("="*70)

        self.analyze_signal_timing(candles_df, signals)
        
        # Преобразуем сигналы в словарь
        signals_dict = {}
        for signal in signals:
            sig_time = pd.to_datetime(signal['timestamp'])
            signals_dict[sig_time] = signal
        
        # Рассчитываем ATR на всех данных
        candles_list = candles_df.to_dict('records')
        atr = self.technical_analyzer.calculate_atr(candles_list)
        
        if not atr:
            logger.error("❌ Не удалось рассчитать ATR")
            return {'error': 'ATR calculation failed'}
        
        logger.info(f"📊 ATR рассчитан: {atr:.4f}")
        
        # Проходим по всем свечам
        for idx, row in candles_df.iterrows():
            current_time = row['timestamp']
            current_price = row['close']
            
            # Обновляем equity curve
            total_equity = self.available_balance
            for pos in self.positions:
                total_equity += pos.quantity * current_price
            self.equity_curve.append({
                'timestamp': current_time,
                'equity': total_equity
            })
            
            # Проверяем торговое время
            if not self.is_trading_hours(current_time):
                continue
            
            # Принудительное закрытие позиций перед концом сессии
            if self.should_close_positions(current_time) and self.positions:
                logger.info(f"\n🌙 {current_time} - Принудительное закрытие позиций (конец сессии)")
                for position in self.positions[:]:
                    await self.close_position(position, current_price, 'end_of_session')
                continue
            
            # Мониторинг открытых позиций
            for position in self.positions[:]:
                should_close = False
                close_reason = None
                close_price = current_price
                
                if position.direction == 'UP':
                    if current_price <= position.stop_loss:
                        should_close = True
                        close_reason = 'stop_loss'
                        close_price = position.stop_loss
                    elif current_price >= position.take_profit:
                        should_close = True
                        close_reason = 'take_profit'
                        close_price = position.take_profit
                else:  # DOWN
                    if current_price >= position.stop_loss:
                        should_close = True
                        close_reason = 'stop_loss'
                        close_price = position.stop_loss
                    elif current_price <= position.take_profit:
                        should_close = True
                        close_reason = 'take_profit'
                        close_price = position.take_profit
                
                if should_close:
                    await self.close_position(position, close_price, close_reason)
            
            # Проверяем наличие сигнала на текущей свече
            if current_time in signals_dict:
                signal = signals_dict[current_time]
                context = signal['context'].upper()
                confidence = signal.get('confidence', 1.0)
                
                logger.info(f"\n📍 {current_time} - Сигнал: {context} (уверенность: {confidence:.2%})")
                
                if context in ['POSITIVE', 'NEGATIVE']:
                    direction = 'UP' if context == 'POSITIVE' else 'DOWN'
                    
                    if len(self.positions) < Config.MAX_OPEN_POSITIONS:
                        position = await self.open_position(
                            ticker=ticker,
                            direction=direction,
                            entry_price=current_price,
                            entry_time=current_time,
                            atr=atr
                        )
                        
                        if position:
                            self.trades_history.append({
                                'timestamp': current_time,
                                'type': 'open',
                                'direction': direction,
                                'price': current_price,
                                'position': position
                            })
        
        # Закрываем оставшиеся позиции
        if self.positions:
            logger.info("\n📉 Закрытие оставшихся позиций...")
            final_price = candles_df.iloc[-1]['close']
            final_time = candles_df.iloc[-1]['timestamp']
            
            for position in self.positions[:]:
                await self.close_position(position, final_price, 'backtest_end')
        
        # Генерируем отчет
        stats = self.get_statistics()
        self.print_report(stats)
        
        # Визуализация
        await self.visualize_results(candles_df, ticker)
        
        return stats
    
    def analyze_signal_timing(self, candles_df: pd.DataFrame, signals: List[Dict]):
        """
        Анализ почему сигналы не привели к сделкам
        
        Args:
            candles_df: DataFrame со свечами
            signals: Список сигналов
        """
        logger.info("\n" + "="*70)
        logger.info("🔍 АНАЛИЗ СИГНАЛОВ")
        logger.info("="*70)
        
        for i, signal in enumerate(signals, 1):
            sig_time = pd.to_datetime(signal['timestamp'])
            context = signal['context'].upper()
            confidence = signal.get('confidence', 1.0)
            
            # Найдем свечу с этой временной меткой
            matching_rows = candles_df[candles_df['timestamp'] == sig_time]
            
            if matching_rows.empty:
                logger.warning(
                    f"⚠️  Сигнал #{i}: {context} @ {sig_time}\n"
                    f"   ❌ Нет свечи в данных на эту дату/время!\n"
                    f"   💡 Проверьте дату в сигнале"
                )
                continue
            
            row = matching_rows.iloc[0]
            current_time = row['timestamp']
            current_price = row['close']
            
            # Проверяем торговое время
            if not self.is_trading_hours(current_time):
                logger.warning(
                    f"⚠️  Сигнал #{i}: {context} @ {sig_time}\n"
                    f"   ❌ Вне торговых часов ({self.session_start} - {self.session_end})\n"
                    f"   Текущее время: {current_time.time()}"
                )
                continue
            
            # Проверяем не пора ли закрывать позиции
            if self.should_close_positions(current_time):
                logger.warning(
                    f"⚠️  Сигнал #{i}: {context} @ {sig_time}\n"
                    f"   ❌ Слишком близко к концу сессии (до {self.close_before_end})"
                )
                continue
            
            # Проверяем баланс
            if self.available_balance < Config.MIN_BALANCE:
                logger.warning(
                    f"⚠️  Сигнал #{i}: {context} @ {sig_time}\n"
                    f"   ❌ Недостаточно средств (текущий баланс: {self.available_balance:.2f})"
                )
                continue
            
            # Проверяем количество открытых позиций
            if len(self.positions) >= Config.MAX_OPEN_POSITIONS:
                logger.warning(
                    f"⚠️  Сигнал #{i}: {context} @ {sig_time}\n"
                    f"   ❌ Достигнут лимит открытых позиций ({Config.MAX_OPEN_POSITIONS})"
                )
                continue
            
            # Если все ОК - статус успеха
            logger.info(
                f"✅ Сигнал #{i}: {context} @ {sig_time}\n"
                f"   Цена: {current_price:.2f} RUB\n"
                f"   Уверенность: {confidence:.2%}\n"
                f"   Статус: ОК для торговли"
            )

    
    
    
    async def open_position(
        self,
        ticker: str,
        direction: str,
        entry_price: float,
        entry_time: datetime,
        atr: float
    ) -> Optional[Position]:
        """Открытие позиции"""
        
        if self.available_balance < Config.MIN_BALANCE:
            return None
        
        # Рассчитываем адаптивные стопы
        stops = self.technical_analyzer.calculate_adaptive_stops(
            entry_price, atr, direction
        )
        
        # Рассчитываем размер позиции
        max_position_value = self.available_balance * (Config.MAX_POSITION_SIZE_PERCENT / 100)
        quantity = int(max_position_value / entry_price)
        
        if quantity < 1:
            return None
        
        position_cost = quantity * entry_price
        
        position = Position(
            ticker=ticker,
            figi=f"FIGI_{ticker}",
            direction=direction,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stops['stop_loss'],
            take_profit=stops['take_profit'],
            strategy='manual_backtest',
            atr=atr
        )
        position.entry_time = entry_time
        
        self.available_balance -= position_cost
        self.positions.append(position)
        
        logger.info(
            f"  📈 ОТКРЫТО: {direction} x{quantity} @ {entry_price:.2f} "
            f"(SL: {stops['stop_loss']:.2f}, TP: {stops['take_profit']:.2f})"
        )
        
        return position
    
    async def close_position(
        self,
        position: Position,
        close_price: float,
        reason: str
    ):
        """Закрытие позиции"""
        
        position.is_closed = True
        position.close_price = close_price
        position.close_time = datetime.now()
        position.close_reason = reason
        position.profit_loss = position.calculate_pnl(close_price)
        
        # Возвращаем средства
        position_value = position.quantity * close_price
        self.available_balance += position_value
        self.current_balance += position.profit_loss
        
        self.positions.remove(position)
        self.closed_positions.append(position)
        
        emoji = "💚" if position.profit_loss > 0 else "💔"
        
        logger.info(
            f"  {emoji} ЗАКРЫТО: {position.direction} @ {close_price:.2f} | "
            f"P/L: {position.profit_loss:+.2f} RUB ({reason})"
        )
        
        self.trades_history.append({
            'timestamp': position.close_time,
            'type': 'close',
            'direction': position.direction,
            'price': close_price,
            'pnl': position.profit_loss,
            'position': position
        })
    
    def get_statistics(self) -> Dict:
        """Получение статистики"""
        
        total_trades = len(self.closed_positions)
        
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'initial_capital': self.initial_capital,
                'final_capital': self.current_balance,
                'total_return': 0.0,
                'max_profit': 0.0,
                'max_loss': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'sharpe_ratio': 0.0
            }
        
        winning_trades = [p for p in self.closed_positions if p.profit_loss > 0]
        losing_trades = [p for p in self.closed_positions if p.profit_loss < 0]
        
        total_pnl = sum(p.profit_loss for p in self.closed_positions)
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0,
            'total_pnl': total_pnl,
            'initial_capital': self.initial_capital,
            'final_capital': self.current_balance,
            'total_return': ((self.current_balance - self.initial_capital) / self.initial_capital) * 100 if self.initial_capital > 0 else 0,
            'max_profit': max((p.profit_loss for p in winning_trades), default=0),
            'max_loss': min((p.profit_loss for p in losing_trades), default=0),
            'avg_profit': sum(p.profit_loss for p in winning_trades) / len(winning_trades) if winning_trades else 0,
            'avg_loss': sum(p.profit_loss for p in losing_trades) / len(losing_trades) if losing_trades else 0,
            'sharpe_ratio': self._calculate_sharpe_ratio()
        }
    
    def _calculate_sharpe_ratio(self) -> float:
        """Расчет коэффициента Шарпа"""
        if not self.equity_curve:
            return 0.0
        
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev_equity = self.equity_curve[i-1]['equity']
            curr_equity = self.equity_curve[i]['equity']
            if prev_equity > 0:
                returns.append((curr_equity - prev_equity) / prev_equity)
        
        if not returns:
            return 0.0
        
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        sharpe = (mean_return / std_return) * np.sqrt(252)
        return sharpe
    
    def print_report(self, stats: Dict):
        """Вывод отчета"""
        
        logger.info("\n" + "="*70)
        logger.info("📊 РЕЗУЛЬТАТЫ БЭКТЕСТИНГА")
        logger.info("="*70)
        logger.info(f"💰 Начальный капитал:  {stats['initial_capital']:.2f} RUB")
        logger.info(f"💰 Конечный капитал:   {stats['final_capital']:.2f} RUB")
        logger.info(f"📈 Прибыль/Убыток:     {stats['total_pnl']:+.2f} RUB")
        logger.info(f"📊 Доходность:         {stats['total_return']:+.2f}%")
        logger.info("─"*70)
        logger.info(f"📊 Всего сделок:       {stats['total_trades']}")
        logger.info(f"✅ Прибыльных:         {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
        logger.info(f"❌ Убыточных:          {stats['losing_trades']}")
        logger.info("─"*70)
        logger.info(f"💚 Лучшая сделка:      +{stats['max_profit']:.2f} RUB")
        logger.info(f"💔 Худшая сделка:      {stats['max_loss']:.2f} RUB")
        logger.info(f"💵 Средняя прибыль:    +{stats['avg_profit']:.2f} RUB")
        logger.info(f"💸 Средний убыток:     {stats['avg_loss']:.2f} RUB")
        logger.info(f"📈 Sharpe Ratio:       {stats['sharpe_ratio']:.2f}")
        logger.info("="*70)

    def _calculate_sma(self, prices: np.ndarray, period: int) -> list:
        """
        Расчет простой скользящей средней (SMA)
        
        Args:
            prices: Массив цен
            period: Период SMA
            
        Returns:
            Список значений SMA
        """
        if len(prices) < period:
            return []
        
        sma = []
        for i in range(len(prices)):
            if i < period - 1:
                sma.append(np.nan)
            else:
                window = prices[i - period + 1:i + 1]
                sma.append(np.mean(window))
        
        return sma

    
    async def visualize_results(self, candles_df: pd.DataFrame, ticker: str):
        """
        Визуализация результатов бэктеста с индикаторами
        
        Args:
            candles_df: DataFrame со свечами
            ticker: Тикер инструмента
        """
        logger.info("\n📊 Создание графиков...")
        
        # Рассчитываем индикаторы
        candles_list = candles_df.to_dict('records')
        atr = self.technical_analyzer.calculate_atr(candles_list)
        
        # Рассчитываем SMA вручную (если метод отсутствует)
        sma_20 = self._calculate_sma(candles_df['close'].values, period=20)
        sma_50 = self._calculate_sma(candles_df['close'].values, period=50)
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 12), sharex=True)
        fig.suptitle(f'Результаты бэктестинга: {ticker} (ATR={atr:.4f})', 
                    fontsize=16, fontweight='bold')
        
        # ===== ГРАФИК 1: Цена + Индикаторы + Сигналы =====
        
        # Рисуем цену
        ax1.plot(candles_df['timestamp'], candles_df['close'], 
                label='Close', color='black', linewidth=1.5, zorder=3)
        
        # Рисуем High/Low как тень
        ax1.fill_between(candles_df['timestamp'], candles_df['low'], candles_df['high'],
                        color='gray', alpha=0.2, label='High/Low')
        
        # Рисуем скользящие средние
        if len(sma_20) > 0:
            ax1.plot(candles_df['timestamp'], sma_20, 
                    label='SMA 20', color='blue', linewidth=1, alpha=0.7, linestyle='--')
        
        if len(sma_50) > 0:
            ax1.plot(candles_df['timestamp'], sma_50, 
                    label='SMA 50', color='red', linewidth=1, alpha=0.7, linestyle='--')
        
        # Добавляем горизонтальные линии ATR для визуализации
        mid_price = candles_df['close'].mean()
        ax1.axhline(y=mid_price + atr*2, color='lightcoral', linestyle=':', alpha=0.5, label=f'ATR*2')
        ax1.axhline(y=mid_price - atr*2, color='lightblue', linestyle=':', alpha=0.5)
        
        # ===== ОТМЕЧАЕМ СИГНАЛЫ =====
        signal_count = 0
        for trade in self.trades_history:
            if trade['type'] == 'open':
                signal_count += 1
                color = 'green' if trade['direction'] == 'UP' else 'red'
                marker = '^' if trade['direction'] == 'UP' else 'v'
                label = f"Entry ({trade['direction']})"
                
                ax1.scatter(trade['timestamp'], trade['price'], 
                        color=color, marker=marker, s=200, zorder=10, 
                        edgecolors='black', linewidth=2, label=label if signal_count == 1 else "")
                
                # Добавляем текст с ценой
                ax1.annotate(f"${trade['price']:.2f}", 
                            xy=(trade['timestamp'], trade['price']),
                            xytext=(10, 10), textcoords='offset points',
                            bbox=dict(boxstyle='round,pad=0.5', fc=color, alpha=0.7),
                            arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color=color))
            
            elif trade['type'] == 'close':
                color = 'lime' if trade['pnl'] > 0 else 'darkred'
                ax1.scatter(trade['timestamp'], trade['price'],
                        color=color, marker='x', s=200, zorder=10, linewidth=3)
                
                # Добавляем P/L
                pnl_text = f"Exit\n{trade['pnl']:+.0f}₽"
                ax1.annotate(pnl_text, 
                            xy=(trade['timestamp'], trade['price']),
                            xytext=(10, -20), textcoords='offset points',
                            bbox=dict(boxstyle='round,pad=0.5', fc=color, alpha=0.7),
                            fontweight='bold')
        
        ax1.set_ylabel('Цена (RUB)', fontsize=12, fontweight='bold')
        ax1.set_title(f'График цены с точками входа/выхода (Всего сделок: {len(self.closed_positions)})', 
                    fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # ===== ГРАФИК 2: Equity Curve =====
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve)
            
            # Основная кривая
            ax2.plot(equity_df['timestamp'], equity_df['equity'],
                    label='Portfolio Value', color='purple', linewidth=2.5, zorder=5)
            
            # Начальный капитал
            ax2.axhline(y=self.initial_capital, color='gray', 
                    linestyle='--', linewidth=2, label='Initial Capital', alpha=0.7)
            
            # Закрашиваем область прибыли/убытка
            ax2.fill_between(equity_df['timestamp'], self.initial_capital, equity_df['equity'],
                            where=(equity_df['equity'] >= self.initial_capital),
                            color='green', alpha=0.3, label='Profit')
            ax2.fill_between(equity_df['timestamp'], self.initial_capital, equity_df['equity'],
                            where=(equity_df['equity'] < self.initial_capital),
                            color='red', alpha=0.3, label='Loss')
        
        ax2.set_ylabel('Капитал (RUB)', fontsize=12, fontweight='bold')
        ax2.set_xlabel('Время', fontsize=12, fontweight='bold')
        ax2.set_title('Кривая доходности (Equity Curve)', fontsize=14, fontweight='bold')
        ax2.legend(loc='upper left', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        # Форматирование оси времени
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        # Сохраняем график
        output_dir = Path('backtest_results')
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / f'{ticker}_backtest_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        logger.info(f"💾 График сохранен: {output_file}")
        
        plt.show()



# Пример использования
async def example_manual_backtest():
    """Пример ручного бэктестинга"""
    
    backtester = ManualBacktester(initial_capital=100000)
    
    # Загружаем данные
    candles_df = backtester.load_candles('data/candles/SBER.csv')
    
    if candles_df.empty:
        logger.error("❌ Нет данных для бэктестинга")
        return
    
    # Берем даты из данных
    first_idx = 50
    mid_idx = len(candles_df) // 2
    last_idx = len(candles_df) - 100
    
    # Сигналы автоматически генерируются из реальных дат
    signals = [
        {
            'timestamp': str(candles_df.iloc[first_idx]['timestamp']),
            'context': 'POSITIVE',
            'confidence': 0.8
        },
        {
            'timestamp': str(candles_df.iloc[mid_idx]['timestamp']),
            'context': 'NEGATIVE',
            'confidence': 0.75
        },
        {
            'timestamp': str(candles_df.iloc[last_idx]['timestamp']),
            'context': 'POSITIVE',
            'confidence': 0.9
        },
    ]
    
    logger.info("📋 Используемые даты для сигналов:")
    for i, sig in enumerate(signals, 1):
        logger.info(f"   {i}. {sig['timestamp']} - {sig['context']} (уверенность: {sig['confidence']:.0%})")
    
    # Запускаем бэктест
    results = await backtester.run_manual_backtest(
        candles_df=candles_df,
        signals=signals,
        #ticker='IMOEXF'
        ticker='SBER'
    )




if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    
    asyncio.run(example_manual_backtest())
