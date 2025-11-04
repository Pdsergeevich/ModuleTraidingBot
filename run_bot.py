"""
Главный скрипт запуска торгового бота
Удобное меню для всех режимов работы
"""

import asyncio
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))


def print_menu():
    """Вывод главного меню"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║           🤖 ТОРГОВЫЙ БОТ v2.1 - ГЛАВНОЕ МЕНЮ 🤖                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

📊 ДОСТУПНЫЕ РЕЖИМЫ:

1. 📥 Скачать исторические данные
   └─ Загрузка свечей для бэктестинга

2. 🧪 Ручной бэктестинг
   └─ Тестирование стратегии с ручными сигналами + визуализация

3. 📝 Demo торговля (Paper Trading)
   └─ Симуляция торговли с реальными данными (рекомендуется!)

4. 🚀 Реальная торговля (Live)
   └─ Боевой режим (только после тщательного тестирования!)

5. 📖 Справка и документация

6. ❌ Выход

══════════════════════════════════════════════════════════════════
    """)


async def download_data_menu():
    """Меню загрузки данных"""
    from data_downloader import DataDownloader
    from datetime import datetime, timedelta
    
    print("\n📥 ЗАГРУЗКА ИСТОРИЧЕСКИХ ДАННЫХ\n")
    print("1. Скачать топ-10 акций (30 дней)")
    print("2. Скачать фьючерс на индекс (30 дней)")
    print("3. Скачать конкретный инструмент")
    print("4. Назад")
    
    choice = input("\nВыберите опцию: ").strip()
    
    # Создаем downloader БЕЗ async with (библиотека работает синхронно)
    downloader = DataDownloader()
    
    try:
        if choice == '1':
            stocks = downloader.get_top_liquid_stocks(limit=10)
            downloader.download_multiple_instruments(
                instruments=stocks,
                days_back=30,
                output_dir="data/candles"
            )
            
        elif choice == '2':
            print("⚠️ Фьючерсы не поддерживаются в этой версии библиотеки")
            print("💡 Используйте опцию 3 и введите тикер, например: RTS-12.24")
            
        elif choice == '3':
            ticker = input("Введите тикер (например, SBER): ").strip().upper()
            days = int(input("Количество дней истории (по умолчанию 30): ").strip() or "30")
            
            try:
                instrument = downloader.session.get_instrument_by_ticker(ticker)
                
                if instrument:
                    downloader.download_candles(
                        figi=instrument.figi,
                        from_date=datetime.now() - timedelta(days=days),
                        to_date=datetime.now(),
                        output_file=f"data/candles/{ticker}.csv"
                    )
                else:
                    print(f"❌ Тикер {ticker} не найден")
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                
        elif choice == '4':
            return
        else:
            print("❌ Неверный выбор")
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()



async def manual_backtest_menu():
    """Меню ручного бэктестинга - использует example_manual_backtest"""
    from advanced_backtester import example_manual_backtest
    await example_manual_backtest()


async def run_demo_trading():
    """Запуск demo торговли"""
    from main import main as run_main
    sys.argv = ['main.py', 'demo']
    await run_main()


async def run_live_trading():
    """Запуск реальной торговли"""
    print("\n⚠️  ВНИМАНИЕ! ВЫ ЗАПУСКАЕТЕ БОЕВОЙ РЕЖИМ!\n")
    print("Убедитесь что:")
    print("✅ Вы протестировали стратегию на истории")
    print("✅ Вы запускали demo режим несколько дней")
    print("✅ Результаты вас устраивают")
    print("✅ Вы понимаете риски\n")
    
    confirm = input("Продолжить? (введите 'ДА' заглавными): ").strip()
    
    if confirm == 'ДА':
        from main import main as run_main
        sys.argv = ['main.py', 'live']
        await run_main()
    else:
        print("❌ Запуск отменен")


def show_help():
    """Показать справку"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                       📖 СПРАВКА                                 ║
╚══════════════════════════════════════════════════════════════════╝

🎯 ПОРЯДОК РАБОТЫ С БОТОМ:

1️⃣ ПОДГОТОВКА
   • Создайте файл .env с API ключами
   • Установите зависимости: pip install -r requirements.txt
   • Для локальной LLM: установите Ollama

2️⃣ СКАЧИВАНИЕ ДАННЫХ
   • Запустите меню '1. Скачать данные'
   • Выберите топ-10 акций или фьючерс
   • Данные сохранятся в data/candles/

3️⃣ ТЕСТИРОВАНИЕ СТРАТЕГИИ
   • Запустите '2. Ручной бэктестинг'
   • Задайте торговые сигналы вручную
   • Изучите графики и статистику
   • Убедитесь что стратегия работает

4️⃣ DEMO ТОРГОВЛЯ
   • Запустите '3. Demo торговля'
   • Бот работает с реальными данными
   • Но сделки только симулируются
   • Прогоняйте несколько дней

5️⃣ РЕАЛЬНАЯ ТОРГОВЛЯ (опционально)
   • Только после успешного тестирования!
   • Запустите '4. Реальная торговля'
   • Начните с минимальных сумм

⚠️  ВАЖНЫЕ ОГРАНИЧЕНИЯ:

• Позиции НЕ переносятся через ночь (закрываются в 23:00)
• Торговля только в будние дни
• При потере связи с рынком - автозакрытие позиций
• Максимальная просадка ограничена

📝 ФАЙЛЫ КОНФИГУРАЦИИ:

• .env - API ключи и токены
• config.py - параметры стратегии
• Не забудьте настроить перед запуском!

═══════════════════════════════════════════════════════════════════
    """)
    input("\nНажмите Enter для продолжения...")


async def main_menu():
    """Главное меню"""
    from datetime import datetime, timedelta
    
    while True:
        print_menu()
        choice = input("Выберите опцию (1-6): ").strip()
        
        if choice == '1':
            await download_data_menu()
            
        elif choice == '2':
            await manual_backtest_menu()
            
        elif choice == '3':
            await run_demo_trading()
            
        elif choice == '4':
            await run_live_trading()
            
        elif choice == '5':
            show_help()
            
        elif choice == '6':
            print("\n👋 До свидания!")
            break
            
        else:
            print("❌ Неверный выбор, попробуйте снова")
        
        input("\nНажмите Enter для возврата в меню...")


if __name__ == '__main__':
    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        print("\n\n👋 Прерывание пользователя. До свидания!")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
