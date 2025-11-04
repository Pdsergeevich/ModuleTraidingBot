"""
Главный файл торгового бота v2.0
Поддержка режимов: live, demo, backtest
Поддержка ИИ: OpenAI, Anthropic, Ollama (локальный)
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
from local_ai_analyzer import LocalAIAnalyzer
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
    """Главный класс торгового бота с улучшенной стратегией"""
    
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
        try:
            validate_config()
        except ValueError as e:
            logger.error(f"❌ Ошибка конфигурации: {e}")
            logger.info("\n💡 Для работы бота необходимо:")
            logger.info("1. Создать файл .env в корне проекта")
            logger.info("2. Добавить в него минимально необходимые переменные:")
            logger.info("   TELEGRAM_API_ID=your_id")
            logger.info("   TELEGRAM_API_HASH=your_hash")
            logger.info("   TINKOFF_TOKEN=your_token")
            logger.info("\n3. Для ИИ-анализа выберите один из вариантов:")
            logger.info("   a) OpenAI: OPENAI_API_KEY=your_key")
            logger.info("   b) Anthropic: ANTHROPIC_API_KEY=your_key")
            logger.info("   c) Локальная LLM: установите Ollama и укажите AI_PROVIDER='local'")
            sys.exit(1)
        
        if self.mode == 'backtest':
            # Режим бэктестинга
            self.backtester = BacktestEngine()
            logger.info("✅ Режим бэктестинга активирован")
        else:
            # Инициализируем ИИ-анализатор в зависимости от провайдера
            await self._initialize_ai_analyzer()
            
            # Инициализируем монитор рынка
            self.market_monitor = MarketMonitor(is_sandbox=Config.SANDBOX_MODE)
            
            if self.mode == 'demo':
                # Paper Trading режим
                self.paper_trading_engine = PaperTradingEngine(
                    initial_capital=Config.BACKTEST_INITIAL_CAPITAL
                )
                logger.info("✅ Paper Trading движок инициализирован")
            else:
                # Реальная торговля
                self.trading_engine = TradingEngine(
                    account_id=Config.TINKOFF_ACCOUNT_ID,
                    is_sandbox=Config.SANDBOX_MODE
                )
            
            # Подключаемся к API
            await self.market_monitor.connect()
            
            if self.mode == 'live':
                await self.trading_engine.connect()
            
            # Создаем Telegram монитор
            self.telegram_monitor = TelegramMonitor(
                on_message_callback=self.handle_telegram_message
            )
            
            logger.info("✅ Все компоненты инициализированы")
    
    async def _initialize_ai_analyzer(self):
        """Инициализация ИИ-анализатора в зависимости от выбранного провайдера"""
        provider = Config.AI_PROVIDER.lower()
        
        logger.info(f"🤖 Инициализация ИИ-анализатора...")
        logger.info(f"   Провайдер: {provider.upper()}")
        
        if provider == 'local':
            # Локальная LLM через Ollama
            try:
                self.ai_analyzer = LocalAIAnalyzer(
                    model=Config.LOCAL_LLM_MODEL,
                    ollama_url=Config.OLLAMA_URL
                )
                logger.info("✅ Локальная LLM подключена")
                logger.info("💰 Режим: ПОЛНОСТЬЮ БЕСПЛАТНЫЙ (без лимитов)")
            except Exception as e:
                logger.error(f"❌ Не удалось инициализировать локальную LLM: {e}")
                logger.info("\n💡 Для использования локальной LLM:")
                logger.info("1. Установите Ollama: https://ollama.com/download")
                logger.info("2. Запустите: ollama serve")
                logger.info(f"3. Загрузите модель: ollama pull {Config.LOCAL_LLM_MODEL}")
                logger.info("\n📝 Или измените AI_PROVIDER в config.py на 'openai' или 'anthropic'")
                sys.exit(1)
        
        elif provider in ['openai', 'anthropic']:
            # OpenAI или Anthropic
            try:
                self.ai_analyzer = AIAnalyzer()
                
                if provider == 'openai':
                    logger.info("✅ OpenAI API подключен")
                    logger.info(f"   Модель: {Config.OPENAI_MODEL}")
                    if not Config.OPENAI_API_KEY:
                        logger.warning("⚠️  OPENAI_API_KEY не установлен!")
                else:
                    logger.info("✅ Anthropic API подключен")
                    logger.info(f"   Модель: {Config.ANTHROPIC_MODEL}")
                    if not Config.ANTHROPIC_API_KEY:
                        logger.warning("⚠️  ANTHROPIC_API_KEY не установлен!")
                
                logger.info("💰 Режим: ПЛАТНЫЙ (расходуются API кредиты)")
            except Exception as e:
                logger.error(f"❌ Не удалось инициализировать {provider.upper()} API: {e}")
                logger.info("\n💡 Альтернативы:")
                logger.info("1. Используйте локальную LLM (бесплатно):")
                logger.info("   - Установите Ollama")
                logger.info("   - Установите AI_PROVIDER='local' в config.py")
                logger.info("2. Получите API ключ:")
                if provider == 'openai':
                    logger.info("   - OpenAI: https://platform.openai.com/api-keys")
                    logger.info("   - Новые пользователи получают $5-18 бесплатно")
                else:
                    logger.info("   - Anthropic: https://console.anthropic.com/")
                sys.exit(1)
        
        else:
            logger.error(f"❌ Неизвестный провайдер ИИ: {provider}")
            logger.info("💡 Доступные провайдеры: 'openai', 'anthropic', 'local'")
            sys.exit(1)
    
    async def handle_telegram_message(self, message_data: Dict):
        """
        Обработка нового сообщения из Telegram с новой стратегией
        
        Args:
            message_data: Данные сообщения
        """
        try:
            logger.info("\n" + "="*70)
            logger.info(f"📨 НОВОЕ СООБЩЕНИЕ из {message_data['channel_name']}")
            logger.info(f"⏰ Время: {message_data['timestamp']}")
            logger.info(f"📝 Текст: {message_data['text'][:200]}...")
            logger.info("="*70)
            
            # ШАГ 1: Анализируем новость с помощью ИИ
            analysis = await self.ai_analyzer.analyze_news(
                message_data['text'],
                message_data['channel_name']
            )
            
            if not analysis:
                logger.info("⏭️  Новость пропущена (не релевантна для торговли)")
                return
            
            ticker = analysis['ticker']
            context = analysis['context']  # POSITIVE, NEGATIVE, NEUTRAL
            direction = analysis['direction']  # UP, DOWN, NEUTRAL
            confidence = analysis['confidence']
            
            logger.info(
                f"🎯 ИИ-АНАЛИЗ:\n"
                f"   Инструмент: {ticker}\n"
                f"   Контекст: {context}\n"
                f"   Направление: {direction}\n"
                f"   Уверенность: {confidence:.2%}\n"
                f"   Сила влияния: {analysis['expected_impact']}\n"
                f"   💡 {analysis['reasoning']}"
            )
            
            # ШАГ 2: Получаем информацию об инструменте
            instrument = await self.market_monitor.get_instrument_by_ticker(ticker)
            
            if not instrument:
                logger.warning(f"⚠️  Инструмент {ticker} не найден на бирже")
                return
            
            logger.info(f"📊 Инструмент: {instrument['name']} ({instrument['figi']})")
            
            # ШАГ 3: Анализируем рыночный контекст (волатильность, ATR, диапазоны)
            market_context = await self.market_monitor.analyze_market_context(
                ticker,
                instrument['figi']
            )
            
            if not market_context:
                logger.warning(f"⚠️  Не удалось проанализировать рыночный контекст для {ticker}")
                return
            
            # ШАГ 4: Выбираем стратегию в зависимости от контекста
            # Определяем какой движок использовать (demo или live)
            engine = self.paper_trading_engine if self.mode == 'demo' else self.trading_engine
            
            position = None
            
            if context in ['POSITIVE', 'NEGATIVE']:
                # Стратегия откатов для трендовых новостей
                logger.info(
                    f"📈 Применение стратегии ОТКАТОВ для {context} контекста"
                )
                
                pullback_result = await self.market_monitor.wait_for_pullback(
                    ticker=ticker,
                    figi=instrument['figi'],
                    expected_direction=direction,
                    market_context=market_context,
                    timeout=Config.PULLBACK_TIMEOUT
                )
                
                if pullback_result and pullback_result['success']:
                    logger.info("✅ ОТКАТ ПОДТВЕРЖДЕН! Открытие позиции...")
                    
                    if engine.can_open_position():
                        position = await engine.open_pullback_position(
                            ticker=ticker,
                            figi=instrument['figi'],
                            direction=direction,
                            entry_price=pullback_result['entry_price'],
                            atr=pullback_result['atr'],
                            lot_size=instrument['lot']
                        )
                        
                        if position:
                            logger.info("🎉 ПОЗИЦИЯ ПО ОТКАТУ УСПЕШНО ОТКРЫТА!")
                            self.save_signal({
                                'timestamp': datetime.now().isoformat(),
                                'mode': self.mode,
                                'news': message_data,
                                'analysis': analysis,
                                'market_context': {
                                    'atr': market_context['atr'],
                                    'volatility': market_context['volatility_percent']
                                },
                                'pullback_result': pullback_result,
                                'position': position.to_dict()
                            })
                else:
                    logger.info("❌ Откат не обнаружен или таймаут")
            
            elif context == 'NEUTRAL' and Config.ENABLE_RANGE_TRADING:
                # Стратегия Range Trading для нейтрального контекста
                logger.info(
                    f"📊 Применение стратегии RANGE TRADING для {context} контекста"
                )
                
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
                        
                        if position:
                            logger.info("🎉 RANGE TRADING ПОЗИЦИЯ ОТКРЫТА!")
                            self.save_signal({
                                'timestamp': datetime.now().isoformat(),
                                'mode': self.mode,
                                'news': message_data,
                                'analysis': analysis,
                                'market_context': {
                                    'atr': market_context['atr'],
                                    'volatility': market_context['volatility_percent']
                                },
                                'range_result': range_result,
                                'position': position.to_dict()
                            })
                else:
                    logger.info("❌ Возможность для Range Trading не найдена")
            else:
                logger.info("⚠️ Range Trading отключен для нейтрального контекста")
        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)
    
    def save_signal(self, signal_data: Dict):
        """
        Сохранение сигнала в историю
        
        Args:
            signal_data: Данные сигнала
        """
        if not Config.SAVE_SIGNALS:
            return
        
        self.signals_history.append(signal_data)
        
        import json
        with open(Config.SIGNALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.signals_history, f, ensure_ascii=False, indent=2)
    
    async def run_live_trading(self):
        """Запуск бота в режиме реальной торговли или demo"""
        mode_name = "DEMO (Paper Trading)" if self.mode == 'demo' else "РЕАЛЬНОЙ ТОРГОВЛИ"
        logger.info(f"🚀 ЗАПУСК БОТА В РЕЖИМЕ {mode_name}")
        logger.info("="*70)
        
        self.is_running = True
        
        # Запускаем мониторинг позиций в отдельной задаче
        if self.mode == 'demo':
            # Для paper trading передаем функцию получения цены
            async def get_price(figi):
                return await self.market_monitor.get_current_price(figi)
            
            monitoring_task = asyncio.create_task(
                self.paper_trading_engine.monitor_positions(get_price)
            )
        else:
            monitoring_task = asyncio.create_task(
                self.trading_engine.monitor_positions()
            )
        
        # Запускаем Telegram монитор (блокирующий вызов)
        try:
            await self.telegram_monitor.start()
        except asyncio.CancelledError:
            logger.info("🛑 Получен сигнал остановки")
        finally:
            # Отменяем задачу мониторинга
            monitoring_task.cancel()
            try:
                await monitoring_task
            except asyncio.CancelledError:
                pass
            
            # Закрываем все открытые позиции
            engine = self.paper_trading_engine if self.mode == 'demo' else self.trading_engine
            
            if engine.positions:
                logger.info("📉 Закрытие всех открытых позиций...")
                for position in engine.positions[:]:
                    current_price = await self.market_monitor.get_current_price(
                        position.figi
                    )
                    if current_price:
                        await engine.close_position(
                            position,
                            float(current_price),
                            'bot_shutdown'
                        )
            
            # Выводим финальную статистику
            if self.mode == 'demo':
                self.paper_trading_engine.print_summary()
            else:
                stats = self.trading_engine.get_statistics()
                logger.info("\n" + "="*70)
                logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
                logger.info("="*70)
                logger.info(f"💰 Начальный баланс:     {stats['initial_balance']:.2f} RUB")
                logger.info(f"💰 Конечный баланс:      {stats['current_balance']:.2f} RUB")
                logger.info(f"📈 Доходность:           {stats['total_return']:+.2f}%")
                logger.info(f"📊 Всего сделок:         {stats['total_trades']}")
                logger.info(f"✅ Прибыльных:           {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
                logger.info(f"❌ Убыточных:            {stats['losing_trades']}")
                logger.info(f"💵 Средняя прибыль:      {stats['avg_pnl']:+.2f} RUB")
                logger.info(f"⏱️  Среднее время сделки: {stats['avg_hold_time']}с")
                logger.info(f"📈 Сделок по откатам:    {stats['pullback_trades']}")
                logger.info(f"📊 Range Trading сделок: {stats['range_trades']}")
                logger.info("="*70)
            
            # Отключаем компоненты
            await self.market_monitor.disconnect()
            if self.mode == 'live':
                await self.trading_engine.disconnect()
    
    async def run_backtest(self):
        """Запуск бота в режиме бэктестинга"""
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
    # Определяем режим работы из аргументов командной строки
    mode = 'demo'  # По умолчанию demo режим
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ['live', 'demo', 'backtest']:
            mode = arg
        else:
            print(f"❌ Неизвестный режим: {arg}")
            print("💡 Доступные режимы: live, demo, backtest")
            print("📝 Пример: python main.py demo")
            sys.exit(1)
    
    # Создаем и запускаем бота
    bot = TradingBot(mode=mode)
    
    # Обработчик сигналов для graceful shutdown
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
    # Выводим баннер
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║    🤖 ТОРГОВЫЙ БОТ v2.0 - УЛУЧШЕННАЯ СТРАТЕГИЯ 🤖               ║
║                                                                  ║
║  📊 Стратегии:                                                  ║
║     • Откаты + Адаптивные стопы (ATR)                          ║
║     • Range Trading для нейтральных новостей                   ║
║                                                                  ║
║  🤖 Поддержка ИИ:                                               ║
║     • OpenAI (платный)                                          ║
║     • Anthropic Claude (платный)                                ║
║     • Ollama - локальные LLM (БЕСПЛАТНО!)                      ║
║                                                                  ║
║  📝 Режимы работы:                                              ║
║     • demo     - Paper Trading (симуляция, рекомендуется)      ║
║     • live     - Реальная торговля (осторожно!)                ║
║     • backtest - Тестирование на истории                       ║
║                                                                  ║
║  🚀 Запуск:                                                     ║
║     python main.py demo      (начните с этого!)                ║
║     python main.py live      (только после тестирования)       ║
║     python main.py backtest  (анализ истории)                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Проверяем наличие необходимых файлов
    import os
    
    if not os.path.exists('.env'):
        print("⚠️  Файл .env не найден!")
        print("\n💡 Создайте файл .env с настройками:")
        print("""
# Telegram API (обязательно)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash

# Tinkoff Invest API (обязательно)
TINKOFF_TOKEN=your_token
TINKOFF_ACCOUNT_ID=your_account_id

# ИИ (выберите один вариант):

# Вариант 1: OpenAI (платно, $5-18 бесплатно для новых пользователей)
OPENAI_API_KEY=your_openai_key

# Вариант 2: Anthropic (платно)
ANTHROPIC_API_KEY=your_anthropic_key

# Вариант 3: Локальная LLM через Ollama (БЕСПЛАТНО!)
# Установите Ollama: https://ollama.com/download
# Затем в config.py установите: AI_PROVIDER = 'local'
        """)
        print("\n📝 После создания .env запустите снова: python main.py demo")
        sys.exit(1)
    
    # Запускаем бота
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
