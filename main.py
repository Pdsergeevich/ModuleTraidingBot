"""
Главный файл торгового бота
Поддержка режимов: live, demo, backtest
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Dict

from config import Config, validate_config
from telegram_monitor import TelegramMonitor
from ai_analyzer import AIAnalyzer
from market_monitor import MarketMonitor
from trading_engine import TradingEngine
from paper_trading import PaperTradingEngine
from backtester import BacktestEngine

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class TradingBot:
    """Главный класс торгового бота"""
    
    def __init__(self, mode: str = 'demo'):
        """
        Инициализация бота
        
        Args:
            mode: Режим работы - 'live', 'demo' или 'backtest'
        """
        self.mode = mode
        self.is_running = False
        
        # Компоненты бота
        self.telegram_monitor = None
        self.ai_analyzer = None
        self.market_monitor = None
        self.trading_engine = None
        self.paper_trading_engine = None
        self.backtester = None
        
        # Хранилище сигналов
        self.signals_history = []
        
    async def initialize(self):
        """Инициализация всех компонентов бота"""
        logger.info("="*70)
        logger.info("🤖 ИНИЦИАЛИЗАЦИЯ ТОРГОВОГО БОТА v2.0")
        logger.info("📊 СТРАТЕГИЯ: Откаты + Адаптивные стопы + Range Trading")
        logger.info(f"⚙️  Режим: {self.mode.upper()}")
        
        if self.mode == 'demo':
            logger.info("📝 DEMO MODE - Все сделки симулируются")
        elif self.mode == 'live':
            logger.info(f"🏖️  {'Песочница' if Config.SANDBOX_MODE else '⚠️  БОЕВОЙ РЕЖИМ'}")
        
        logger.info("="*70)
        
        # Проверяем конфигурацию
        validate_config()
        
        if self.mode == 'backtest':
            self.backtester = BacktestEngine()
            logger.info("✅ Режим бэктестинга активирован")
        else:
            self.ai_analyzer = AIAnalyzer()
            self.market_monitor = MarketMonitor(is_sandbox=Config.SANDBOX_MODE)
            
            if self.mode == 'demo':
                # Paper Trading режим
                self.paper_trading_engine = PaperTradingEngine(
                    initial_capital=Config.BACKTEST_INITIAL_CAPITAL
                )
            else:
                # Реальная торговля
                self.trading_engine = TradingEngine(
                    account_id=Config.TINKOFF_ACCOUNT_ID,
                    is_sandbox=Config.SANDBOX_MODE
                )
                await self.trading_engine.connect()
            
            await self.market_monitor.connect()
            
            self.telegram_monitor = TelegramMonitor(
                on_message_callback=self.handle_telegram_message
            )
            
            logger.info("✅ Все компоненты инициализированы")
    
    async def handle_telegram_message(self, message_data: Dict):
        """Обработка нового сообщения из Telegram"""
        try:
            logger.info("\n" + "="*70)
            logger.info(f"📨 НОВОЕ СООБЩЕНИЕ из {message_data['channel_name']}")
            logger.info(f"⏰ Время: {message_data['timestamp']}")
            logger.info(f"📝 Текст: {message_data['text'][:200]}...")
            logger.info("="*70)
            
            # ШАГ 1: ИИ-анализ
            analysis = await self.ai_analyzer.analyze_news(
                message_data['text'],
                message_data['channel_name']
            )
            
            if not analysis:
                logger.info("⏭️  Новость пропущена")
                return
            
            ticker = analysis['ticker']
            context = analysis['context']
            direction = analysis['direction']
            confidence = analysis['confidence']
            
            logger.info(
                f"🎯 ИИ-АНАЛИЗ:\n"
                f"   Инструмент: {ticker}\n"
                f"   Контекст: {context}\n"
                f"   Уверенность: {confidence:.2%}"
            )
            
            # ШАГ 2: Получаем инструмент
            instrument = await self.market_monitor.get_instrument_by_ticker(ticker)
            
            if not instrument:
                logger.warning(f"⚠️  Инструмент {ticker} не найден")
                return
            
            # ШАГ 3: Анализ рынка
            market_context = await self.market_monitor.analyze_market_context(
                ticker,
                instrument['figi']
            )
            
            if not market_context:
                logger.warning(f"⚠️  Не удалось проанализировать рынок для {ticker}")
                return
            
            # Выбираем движок (demo или live)
            engine = self.paper_trading_engine if self.mode == 'demo' else self.trading_engine
            
            # ШАГ 4: Выполняем торговую логику
            position = None
            
            if context in ['POSITIVE', 'NEGATIVE']:
                # Стратегия откатов
                logger.info(f"📈 Стратегия ОТКАТОВ для {context} контекста")
                
                pullback_result = await self.market_monitor.wait_for_pullback(
                    ticker=ticker,
                    figi=instrument['figi'],
                    expected_direction=direction,
                    market_context=market_context,
                    timeout=Config.PULLBACK_TIMEOUT
                )
                
                if pullback_result and pullback_result['success']:
                    logger.info("✅ ОТКАТ ПОДТВЕРЖДЕН!")
                    
                    if engine.can_open_position():
                        position = await engine.open_pullback_position(
                            ticker=ticker,
                            figi=instrument['figi'],
                            direction=direction,
                            entry_price=pullback_result['entry_price'],
                            atr=pullback_result['atr'],
                            lot_size=instrument['lot']
                        )
            
            elif context == 'NEUTRAL' and Config.ENABLE_RANGE_TRADING:
                # Стратегия Range Trading
                logger.info(f"📊 Стратегия RANGE TRADING для {context} контекста")
                
                range_result = await self.market_monitor.monitor_range_trading_opportunity(
                    ticker=ticker,
                    figi=instrument['figi'],
                    market_context=market_context,
                    timeout=300
                )
                
                if range_result and range_result['success']:
                    logger.info("✅ НАЙДЕНА ВОЗМОЖНОСТЬ RANGE TRADING!")
                    
                    if engine.can_open_position():
                        position = await engine.open_range_trading_position(
                            ticker=ticker,
                            figi=instrument['figi'],
                            direction=range_result['direction'],
                            entry_price=range_result['entry_price'],
                            stop_loss=range_result['stop_loss'],
                            take_profit=range_result['take_profit'],
                            lot_size=instrument['lot']
                        )
            
            # Сохраняем сигнал
            if position and Config.SAVE_SIGNALS:
                self.save_signal({
                    'timestamp': datetime.now().isoformat(),
                    'mode': self.mode,
                    'news': message_data,
                    'analysis': analysis,
                    'position': position.to_dict()
                })
        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)
    
    def save_signal(self, signal_data: Dict):
        """Сохранение сигнала"""
        self.signals_history.append(signal_data)
        
        import json
        with open(Config.SIGNALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.signals_history, f, ensure_ascii=False, indent=2)
    
    async def run_live_trading(self):
        """Запуск в режиме live или demo"""
        mode_name = "DEMO (Paper Trading)" if self.mode == 'demo' else "РЕАЛЬНОЙ ТОРГОВЛИ"
        logger.info(f"🚀 ЗАПУСК БОТА В РЕЖИМЕ {mode_name}")
        logger.info("="*70)
        
        self.is_running = True
        
        # Выбираем engine для мониторинга
        if self.mode == 'demo':
            # Для paper trading создаем функцию получения цены
            async def get_price(figi):
                return await self.market_monitor.get_current_price(figi)
            
            monitoring_task = asyncio.create_task(
                self.paper_trading_engine.monitor_positions(get_price)
            )
        else:
            monitoring_task = asyncio.create_task(
                self.trading_engine.monitor_positions()
            )
        
        try:
            await self.telegram_monitor.start()
        except asyncio.CancelledError:
            logger.info("🛑 Получен сигнал остановки")
        finally:
            monitoring_task.cancel()
            
            # Закрываем позиции
            engine = self.paper_trading_engine if self.mode == 'demo' else self.trading_engine
            
            if engine.positions:
                logger.info("📉 Закрытие всех открытых позиций...")
                for position in engine.positions[:]:
                    current_price = await self.market_monitor.get_current_price(position.figi)
                    if current_price:
                        await engine.close_position(
                            position,
                            float(current_price),
                            'bot_shutdown'
                        )
            
            # Статистика
            if self.mode == 'demo':
                self.paper_trading_engine.print_summary()
            else:
                stats = self.trading_engine.get_statistics()
                # ... (вывод статистики как раньше)
            
            await self.market_monitor.disconnect()
            if self.mode == 'live':
                await self.trading_engine.disconnect()
    
    async def run_backtest(self):
        """Запуск бэктестинга"""
        results = await self.backtester.run_backtest()
        
        if 'error' not in results:
            self.backtester.export_results()
    
    async def start(self):
        """Запуск бота"""
        await self.initialize()
        
        if self.mode == 'backtest':
            await self.run_backtest()
        else:
            await self.run_live_trading()
    
    async def stop(self):
        """Остановка бота"""
        logger.info("🛑 Остановка бота...")
        self.is_running = False
        
        if self.telegram_monitor:
            await self.telegram_monitor.stop()


async def main():
    """Главная функция"""
    # Определяем режим из аргументов
    mode = 'demo'  # По умолчанию demo
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ['live', 'demo', 'backtest']:
            mode = arg
    
    bot = TradingBot(mode=mode)
    
    def signal_handler(sig, frame):
        logger.info("\n🛑 Получен сигнал остановки...")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("🛑 Прерывание пользователя")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        await bot.stop()


if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║    🤖 ТОРГОВЫЙ БОТ v2.0 - УЛУЧШЕННАЯ СТРАТЕГИЯ 🤖               ║
║                                                                  ║
║  📊 Режимы работы:                                              ║
║     • demo     - Paper Trading (симуляция без реальных сделок) ║
║     • live     - Реальная торговля (песочница или боевой)      ║
║     • backtest - Тестирование на исторических данных           ║
║                                                                  ║
║  📈 Запуск: python main.py [demo|live|backtest]                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
