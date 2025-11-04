"""
Файл конфигурации торгового бота v2.1
Добавлены настройки времени торговли и обработки ошибок
"""

import os
from datetime import time as dt_time
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
    TINKOFF_ACCOUNT_ID = os.getenv('TINKOFF_ACCOUNT_ID', None)
    SANDBOX_MODE = True
    
    # ============= ТОРГОВОЕ ВРЕМЯ =============
    # Время начала торговой сессии (МСК)
    TRADING_SESSION_START = dt_time(10, 0)  # 10:00
    
    # Время окончания торговой сессии (МСК)
    TRADING_SESSION_END = dt_time(23, 30)  # 23:30
    
    # Время принудительного закрытия всех позиций (МСК)
    # Позиции НЕ переносятся через ночь!
    FORCE_CLOSE_TIME = dt_time(23, 0)  # 23:00
    
    # Запрещать открытие новых позиций за N минут до закрытия
    NO_NEW_POSITIONS_BEFORE_CLOSE_MINUTES = 60  # За 1 час
    
    # Торговля по дням недели (0=Пн, 6=Вс)
    TRADING_DAYS = [0, 1, 2, 3, 4]  # Пн-Пт, без выходных
    
    # ============= ИИ НАСТРОЙКИ =============
    AI_PROVIDER = 'local'  # 'openai', 'anthropic', 'local'
    
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = 'gpt-4-turbo-preview'
    
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL = 'claude-3-sonnet-20240229'
    
    # Локальная LLM (Ollama)
    LOCAL_LLM_MODEL = 'llama3.2:3b'
    OLLAMA_URL = 'http://localhost:11434'
    
    MIN_AI_CONFIDENCE = 0.65
    
    # ============= СТРАТЕГИЯ ОТКАТОВ =============
    FIBONACCI_ENTRY_LEVELS = [0.382, 0.5, 0.618]
    PULLBACK_TIMEOUT = 300
    MIN_TREND_MOVEMENT = 0.5
    FIBONACCI_TOLERANCE = 0.3
    
    # ============= АДАПТИВНЫЕ СТОПЫ (ATR) =============
    ATR_PERIOD = 14
    ATR_STOP_MULTIPLIER = 2.0
    ATR_TAKE_MULTIPLIER = 3.0
    MIN_STOP_LOSS_PERCENT = 1.0
    MAX_STOP_LOSS_PERCENT = 5.0
    
    # ============= RANGE TRADING =============
    ENABLE_RANGE_TRADING = True
    MIN_RANGE_WIDTH_PERCENT = 2.0
    MAX_RANGE_WIDTH_PERCENT = 10.0
    RANGE_ENTRY_OFFSET = 0.1
    RANGE_STOP_PERCENT = 0.3
    
    # ============= ВОЛАТИЛЬНОСТЬ =============
    HISTORICAL_DAYS = 7
    CANDLE_INTERVAL = '1min'
    MIN_VOLATILITY_PERCENT = 0.5
    MAX_VOLATILITY_PERCENT = 15.0
    
    # ============= ТОРГОВЫЕ ПАРАМЕТРЫ =============
    MAX_POSITION_SIZE_PERCENT = 5
    MAX_OPEN_POSITIONS = 3
    
    # ============= РИСК-МЕНЕДЖМЕНТ =============
    MAX_DRAWDOWN_PERCENT = 10.0
    MIN_BALANCE = 10000
    MIN_RISK_REWARD_RATIO = 1.5
    
    # ============= ОБРАБОТКА ОШИБОК =============
    # Максимальное количество попыток получения данных
    MAX_RETRY_ATTEMPTS = 3
    
    # Задержка между попытками (секунды)
    RETRY_DELAY = 5
    
    # Таймаут ожидания ответа от API (секунды)
    API_TIMEOUT = 30
    
    # Максимальное время без обновления цены (секунды)
    # Если цена не обновляется - закрываем позиции
    MAX_PRICE_STALE_TIME = 60
    
    # Закрывать ли позиции при потере связи с рынком
    CLOSE_ON_CONNECTION_LOSS = True
    
    # Уведомлять ли о критических ошибках
    ALERT_ON_CRITICAL_ERRORS = True
    
    # ============= БЭКТЕСТИНГ =============
    BACKTEST_NEWS_FILE = 'data/historical_news.json'
    BACKTEST_PRICES_FILE = 'data/historical_prices.csv'
    BACKTEST_INITIAL_CAPITAL = 100000
    
    # Директория для результатов бэктестинга
    BACKTEST_RESULTS_DIR = 'backtest_results'
    
    # ============= ИНСТРУМЕНТЫ =============
    # Предпочтительные инструменты для торговли
    PREFERRED_INSTRUMENTS = [
        'SBER',   # Сбербанк
        'GAZP',   # Газпром
        'LKOH',   # Лукойл
        'YNDX',   # Яндекс
        'GMKN',   # Норникель
    ]
    
    # Фьючерсы на индексы (более предсказуемы для новостей)
    ENABLE_FUTURES_TRADING = True
    PREFERRED_FUTURES = [
        'RTS',    # Фьючерс на индекс РТС
        'MIX',    # Фьючерс на индекс ММВБ
    ]
    
    # ============= ЛОГИРОВАНИЕ =============
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'trading_bot.log'
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
