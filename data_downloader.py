"""
Модуль загрузки исторических данных
Официальная библиотека Tinkoff Invest API
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict
import pandas as pd
from pathlib import Path

# Импорты для официальной библиотеки
from tinkoff.invest import Client, CandleInterval, InstrumentIdType
from tinkoff.invest.utils import now

from config import Config

logger = logging.getLogger(__name__)


class DataDownloader:
    """Класс для загрузки исторических данных"""
    
    def __init__(self, token: str = None):
        """
        Инициализация загрузчика
        
        Args:
            token: Токен Tinkoff Invest API
        """
        self.token = token or Config.TINKOFF_TOKEN
    
    def get_top_liquid_stocks(self, limit: int = 10) -> List[Dict]:
        """Получение топ ликвидных акций"""
        logger.info(f"📊 Получение топ-{limit} акций...")
        
        with Client(self.token) as client:
            # Получаем все акции
            shares = client.instruments.shares()
            
            # Фильтруем российские
            russian_stocks = [
                share for share in shares.instruments
                if share.currency == 'rub'
            ]
            
            # Топ-10 по популярности
            top_tickers = ['SBER', 'GAZP', 'LKOH', 'YNDX', 'GMKN', 'NVTK', 'ROSN', 'TATN', 'MGNT', 'MTSS']
            
            result = []
            for ticker in top_tickers[:limit]:
                stock = next((s for s in russian_stocks if s.ticker == ticker), None)
                if stock:
                    result.append({
                        'ticker': stock.ticker,
                        'figi': stock.figi,
                        'name': stock.name,
                        'lot': stock.lot,
                        'currency': stock.currency
                    })
                    logger.info(f"   ✅ {ticker} - {stock.name}")
            
            return result
    
    def get_index_futures(self) -> List[Dict]:
        """Получение фьючерсов на индексы"""
        logger.info("📈 Получение фьючерсов на индексы...")
        
        with Client(self.token) as client:
            futures = client.instruments.futures()
            
            # Фильтруем по названию
            index_futures = []
            for fut in futures.instruments:
                if any(keyword in fut.ticker for keyword in ['RTS', 'MIX', 'IMOEX']):
                    # Только активные контракты
                    if fut.expiration_date and fut.expiration_date.replace(tzinfo=None) > datetime.now():
                        index_futures.append({
                            'ticker': fut.ticker,
                            'figi': fut.figi,
                            'name': fut.name,
                            'lot': fut.lot,
                            'expiration_date': fut.expiration_date
                        })
            
            # Сортируем по дате экспирации
            index_futures.sort(key=lambda x: x['expiration_date'])
            
            logger.info(f"✅ Найдено {len(index_futures)} фьючерсов")
            for fut in index_futures[:5]:
                logger.info(f"   {fut['ticker']} - {fut['name']}")
            
            return index_futures
    
    def download_candles(
        self,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: CandleInterval = CandleInterval.CANDLE_INTERVAL_1_MIN,
        output_file: str = None
    ) -> pd.DataFrame:
        """
        Скачивание свечей
        
        Args:
            figi: FIGI инструмента
            from_date: Дата начала
            to_date: Дата окончания
            interval: Интервал свечей
            output_file: Путь для сохранения
            
        Returns:
            DataFrame со свечами
        """
        logger.info(f"📥 Загрузка свечей...")
        logger.info(f"   FIGI: {figi}")
        logger.info(f"   Период: {from_date.strftime('%Y-%m-%d')} - {to_date.strftime('%Y-%m-%d')}")
        
        candles_data = []
        
        try:
            with Client(self.token) as client:
                # Получаем свечи
                for candle in client.get_all_candles(
                    figi=figi,
                    from_=from_date,
                    to=to_date,
                    interval=interval
                ):
                    candles_data.append({
                        'timestamp': candle.time,
                        'open': self._quotation_to_float(candle.open),
                        'high': self._quotation_to_float(candle.high),
                        'low': self._quotation_to_float(candle.low),
                        'close': self._quotation_to_float(candle.close),
                        'volume': candle.volume
                    })
            
            df = pd.DataFrame(candles_data)
            
            if df.empty:
                logger.warning("⚠️ Данные не найдены")
                return df
            
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            logger.info(f"✅ Загружено {len(df)} свечей")
            logger.info(f"   Первая: {df.iloc[0]['timestamp']}")
            logger.info(f"   Последняя: {df.iloc[-1]['timestamp']}")
            
            if output_file:
                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(output_file, index=False)
                logger.info(f"💾 Сохранено: {output_file}")
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
    
    def _quotation_to_float(self, quotation) -> float:
        """Преобразование Quotation в float"""
        if quotation is None:
            return 0.0
        return float(quotation.units) + float(quotation.nano) / 1e9
    
    def download_multiple_instruments(
        self,
        instruments: List[Dict],
        days_back: int = 30,
        interval: CandleInterval = CandleInterval.CANDLE_INTERVAL_1_MIN,
        output_dir: str = "data/candles"
    ):
        """Скачать несколько инструментов"""
        logger.info(f"📦 Загрузка {len(instruments)} инструментов")
        
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days_back)
        
        for i, inst in enumerate(instruments, 1):
            logger.info(f"\n[{i}/{len(instruments)}] {inst['ticker']}")
            
            self.download_candles(
                figi=inst['figi'],
                from_date=from_date,
                to_date=to_date,
                interval=interval,
                output_file=f"{output_dir}/{inst['ticker']}.csv"
            )
            
            import time
            time.sleep(0.5)
        
        logger.info(f"\n✅ Загрузка завершена! Данные в {output_dir}/")


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Загрузка исторических данных')
    parser.add_argument('--days', type=int, default=30, help='Количество дней')
    parser.add_argument('--ticker', type=str, help='Тикер (SBER, GAZP и т.д.)')
    parser.add_argument('--futures', action='store_true', help='Загрузить фьючерсы')
    parser.add_argument('--interval', type=str, default='1min',
                       choices=['1min', '5min', '15min', '1hour', '1day'])
    
    args = parser.parse_args()
    
    # Маппинг интервалов
    interval_map = {
        '1min': CandleInterval.CANDLE_INTERVAL_1_MIN,
        '5min': CandleInterval.CANDLE_INTERVAL_5_MIN,
        '15min': CandleInterval.CANDLE_INTERVAL_15_MIN,
        '1hour': CandleInterval.CANDLE_INTERVAL_HOUR,
        '1day': CandleInterval.CANDLE_INTERVAL_DAY
    }
    
    print("""
╔══════════════════════════════════════════════════════════════════╗
║          📥 ЗАГРУЗЧИК ИСТОРИЧЕСКИХ ДАННЫХ                        ║
║          (Официальная библиотека Tinkoff)                        ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    downloader = DataDownloader()
    interval = interval_map[args.interval]
    
    if args.ticker:
        # Конкретный тикер
        with Client(downloader.token) as client:
            shares = client.instruments.shares()
            instrument = next((s for s in shares.instruments if s.ticker == args.ticker), None)
            
            if instrument:
                downloader.download_candles(
                    figi=instrument.figi,
                    from_date=datetime.now() - timedelta(days=args.days),
                    to_date=datetime.now(),
                    interval=interval,
                    output_file=f"data/candles/{args.ticker}.csv"
                )
            else:
                print(f"❌ Тикер {args.ticker} не найден")
    
    elif args.futures:
        # Фьючерсы
        futures = downloader.get_index_futures()
        if futures:
            downloader.download_candles(
                figi=futures[0]['figi'],
                from_date=datetime.now() - timedelta(days=args.days),
                to_date=datetime.now(),
                interval=interval,
                output_file=f"data/candles/{futures[0]['ticker']}.csv"
            )
    else:
        # Топ-10 акций
        stocks = downloader.get_top_liquid_stocks(10)
        downloader.download_multiple_instruments(
            stocks,
            days_back=args.days,
            interval=interval
        )
    
    print("\n✅ Готово!")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    main()
