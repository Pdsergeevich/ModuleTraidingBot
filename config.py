"""
Файл конфигурации торгового бота
Стратегия с откатами, адаптивными стопами и Range Trading
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Основная конфигурация бота"""
    
    # ============= TELEGRAM НАСТРОЙКИ =============
    TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
    TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
    TELEGRAM_SESSION_NAME = 'trading_bot_session'
    
    TELEGRAM_CHANNELS = [
        '@MarketTwits',
        '@AK47pfl',
        '@inside_trade_robot',
        '@MoscowExchangeOfficial'
    ]
    
    # ============= TINKOFF INVEST НАСТРОЙКИ =============
    TINKOFF_TOKEN = os.getenv('TINKOFF_TOKEN')
    TINKOFF_ACCOUNT_ID = os.getenv('TINKOFF_ACCOUNT_ID')
    SANDBOX_MODE = True
    
    # ============= ИИ НАСТРОЙКИ =============
    AI_PROVIDER = 'openai'
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = 'gpt-4-turbo-preview'
    
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL = 'claude-3-sonnet-20240229'
    
    # Минимальная уверенность ИИ для рассмотрения сигнала (0-1)
    MIN_AI_CONFIDENCE = 0.65
    
    # ============= СТРАТЕГИЯ ОТКАТОВ =============
    # Уровни Фибоначчи для входа на откатах
    FIBONACCI_ENTRY_LEVELS = [0.382, 0.5, 0.618]  # 38.2%, 50%, 61.8%
    
    # Максимальное время ожидания отката (в секундах)
    PULLBACK_TIMEOUT = 300  # 5 минут
    
    # Минимальное движение для определения тренда (в процентах)
    MIN_TREND_MOVEMENT = 0.5
    
    # Допустимое отклонение от уровня Фибоначчи (в процентах)
    FIBONACCI_TOLERANCE = 0.3
    
    # ============= АДАПТИВНЫЕ СТОПЫ НА ОСНОВЕ ATR =============
    # Период для расчета ATR (количество свечей)
    ATR_PERIOD = 14
    
    # Мультипликатор ATR для stop-loss
    ATR_STOP_MULTIPLIER = 2.0
    
    # Мультипликатор ATR для take-profit
    ATR_TAKE_MULTIPLIER = 3.0
    
    # Минимальный stop-loss в процентах (страховка)
    MIN_STOP_LOSS_PERCENT = 1.0
    
    # Максимальный stop-loss в процентах (страховка)
    MAX_STOP_LOSS_PERCENT = 5.0
    
    # ============= RANGE TRADING (НЕЙТРАЛЬНЫЙ КОНТЕКСТ) =============
    # Включить ли торговлю в диапазоне при нейтральном контексте
    ENABLE_RANGE_TRADING = True
    
    # Минимальная ширина диапазона для торговли (в процентах)
    MIN_RANGE_WIDTH_PERCENT = 2.0
    
    # Максимальная ширина диапазона (в процентах)
    MAX_RANGE_WIDTH_PERCENT = 10.0
    
    # Отступ от границ диапазона для входа (в процентах от ширины)
    RANGE_ENTRY_OFFSET = 0.1  # 10% от ширины диапазона
    
    # Stop-loss для Range Trading (в процентах от ширины диапазона)
    RANGE_STOP_PERCENT = 0.3  # 30% от ширины диапазона
    
    # ============= ВОЛАТИЛЬНОСТЬ И ИСТОРИЧЕСКИЕ ДАННЫЕ =============
    # Период исторических данных для анализа (в днях)
    HISTORICAL_DAYS = 7
    
    # Интервал свечей для анализа
    CANDLE_INTERVAL = '1min'  # 1min, 5min, 15min, 1hour, 1day
    
    # Минимальная волатильность для входа (в процентах)
    MIN_VOLATILITY_PERCENT = 0.5
    
    # Максимальная волатильность (слишком опасно торговать)
    MAX_VOLATILITY_PERCENT = 15.0
    
    # ============= ТОРГОВЫЕ ПАРАМЕТРЫ =============
    # Максимальный размер позиции от портфеля (в процентах)
    MAX_POSITION_SIZE_PERCENT = 5
    
    # Максимальное количество одновременных открытых позиций
    MAX_OPEN_POSITIONS = 3
    
    # ============= РИСК-МЕНЕДЖМЕНТ =============
    # Максимальная просадка портфеля (в процентах)
    MAX_DRAWDOWN_PERCENT = 10.0
    
    # Минимальный баланс для торговли (в рублях)
    MIN_BALANCE = 10000
    
    # Risk/Reward соотношение (минимальное)
    MIN_RISK_REWARD_RATIO = 1.5
    
    # ============= БЭКТЕСТИНГ =============
    BACKTEST_NEWS_FILE = 'historical_news.json'
    BACKTEST_PRICES_FILE = 'historical_prices.csv'
    BACKTEST_INITIAL_CAPITAL = 100000
    
    # ============= ЛОГИРОВАНИЕ =============
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'trading_bot.log'
    
    # Сохранять ли все сигналы в файл
    SAVE_SIGNALS = True
    SIGNALS_FILE = 'signals.json'
    
    # ============= ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ =============
    UPDATE_INTERVAL = 1


def validate_config():
    """Проверяет наличие всех необходимых настроек"""
    required_vars = [
        'TELEGRAM_API_ID',
        'TELEGRAM_API_HASH',
        'TINKOFF_TOKEN',
        'OPENAI_API_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not getattr(Config, var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(
            f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}\n"
            f"Создайте файл .env и добавьте их туда"
        )


if __name__ == '__main__':
    try:
        validate_config()
        print("✅ Конфигурация валидна")
    except ValueError as e:
        print(f"❌ Ошибка конфигурации: {e}")
