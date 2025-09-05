import requests
from datetime import datetime, timedelta
from enum import Enum
import time
from django.db import transaction

from Database.models import Symbol, Candle

BASE_URL = "https://api.bitget.com/api/v2/spot/market/history-candles"


class Interval(Enum):
    MIN_1 = ("1min", 1 * 60 * 1000)  # 1 minute
    MIN_3 = ("3min", 3 * 60 * 1000)  # 3 minutes
    MIN_5 = ("5min", 5 * 60 * 1000)  # 5 minutes
    MIN_15 = ("15min", 15 * 60 * 1000)  # 15 minutes
    MIN_30 = ("30min", 30 * 60 * 1000)  # 30 minutes
    HOUR_1 = ("1h", 60 * 60 * 1000)  # 1 hour
    HOUR_4 = ("4h", 4 * 60 * 60 * 1000) # 4 hour
    DAY_1 = ("1day", 24 * 60 * 60 * 1000)  # 1 day

    def api_format(self):
        """Return the API format (e.g., '1min')."""
        return self.value[0]

    def to_db_format(self):
        """Return the millisecond duration for database storage."""
        return self.value[1]


class CandleAgent:
    def __init__(self, symbol="BTCUSDT", interval=Interval.MIN_15):
        self.interval = interval
        self.symbol = self._validate_symbol(symbol)

    def _validate_symbol(self, symbol):
        try:
            symbol_obj, created = Symbol.objects.get_or_create(symbol=symbol)
            return symbol_obj.symbol
        except Exception as e:
            available_symbols = list(Symbol.objects.values_list('symbol', flat=True))
            raise ValueError(f"Symbol {symbol} not found in database. Available symbols: {available_symbols}") from e

    def get_time_range(self, days=30, hours=0):
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days, hours=hours)).timestamp() * 1000)
        return start_time, end_time

    def fetch_candles(self, end_time, limit=100):
        query_string = f"?symbol={self.symbol}&granularity={self.interval.api_format()}&endTime={end_time}&limit={limit}"
        url = BASE_URL + query_string
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "00000" and isinstance(data.get("data"), list):
                return data["data"]
            print(f"Error: {data.get('msg', 'Unknown error')}")
            return []
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            return []

    def fetch_past_candles(self, days=30, hours=0, limit=100):
        oldest_candle = Candle.objects.filter(
            symbol__symbol=self.symbol,
            interval=self.interval.to_db_format()
        ).first()

        if not oldest_candle:
            print("No data in database for this symbol and interval. Use fetch_candles_range instead.")
            return []

        end_time = oldest_candle.open_time
        start_time = int(
            (datetime.fromtimestamp(end_time / 1000) - timedelta(days=days, hours=hours)).timestamp() * 1000)
        return self.fetch_candles_range(start_time, end_time, limit)

    def fetch_future_candles(self, limit=100):
        newest_candle = Candle.objects.filter(
            symbol__symbol=self.symbol,
            interval=self.interval.to_db_format()
        ).last()

        if not newest_candle:
            print("No data in database for this symbol and interval. Use fetch_candles_range instead.")
            return []

        start_time = newest_candle.open_time
        end_time = int(datetime.now().timestamp() * 1000)
        return self.fetch_candles_range(start_time, end_time, limit)

    def fetch_candles_range(self, start_time, end_time, limit=100):
        all_candles = []
        current_end = end_time
        while current_end > start_time:
            candles = self.fetch_candles(current_end, limit)
            if candles:
                all_candles.extend(candles)
                if len(candles) < limit:
                    break
                current_end = int(candles[0][0])
            else:
                break
            time.sleep(0.2)
        all_candles.sort(key=lambda x: int(x[0]))
        return all_candles

    @transaction.atomic
    def save_to_db(self, candles):
        if not candles:
            print("No data to save.")
            return 0

        try:
            symbol_obj = Symbol.objects.get(symbol=self.symbol)
            saved_count = 0

            for candle in candles:
                candle_obj, created = Candle.objects.update_or_create(
                    open_time=int(candle[0]),
                    symbol=symbol_obj,
                    interval=self.interval.to_db_format(),
                    defaults={
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'base_volume': float(candle[5]),
                        'usdt_volume': float(candle[6]),
                        'quote_volume': float(candle[7])
                    }
                )
                if created:
                    saved_count += 1

            print(
                f"Saved/updated {len(candles)} rows to candles table for {self.symbol} (interval: {self.interval.to_db_format()}ms).")
            return saved_count

        except Exception as e:
            print(f"Error saving data: {e}")
            raise

    def check_candles_consistency(self):
        candles = Candle.objects.filter(symbol__symbol=self.symbol, interval=self.interval.value[1])
        flag = True
        for previous_candle, candle in zip(candles, candles[1:]):
            if previous_candle.open_time + self.interval.value[1] != candle.open_time:
                flag = False
                print(previous_candle.open_time)
                break
        if flag:
            print("OKAY")


def main():
    try:
        agent = CandleAgent(symbol="ETHUSDT", interval=Interval.HOUR_4)
        start_time, end_time = agent.get_time_range(days=30)
        candles = agent.fetch_candles_range(start_time, end_time)
        agent.save_to_db(candles)

        for i in range(10):
            print(i)
            candles = agent.fetch_past_candles(days=10)
            agent.save_to_db(candles)

        # candles = agent.fetch_future_candles()
        # agent.save_to_db(candles)

    except ValueError as e:
        print(f"Initialization failed: {e}")

