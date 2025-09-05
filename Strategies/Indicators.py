from abc import ABC, abstractmethod

import pandas as pd
import talib

from Database.models import Candle


class Oscillator(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def calculate(self):
        raise NotImplementedError


class RSI(Oscillator):
    def __init__(self, symbol, interval, period=14, limit=10000):

        super().__init__()
        self.symbol = symbol
        self.interval = interval
        self.period = period
        self.limit = limit

    def calculate(self):
        candles = Candle.objects.filter(symbol=self.symbol, interval=self.interval)[:self.limit]
        if not candles.exists():
            raise ValueError(f"هیچ کندلی برای نماد {self.symbol} و تایم‌فریم {self.interval} پیدا نشد.")

        data = pd.DataFrame.from_records(candles.values('open_time', 'close'))
        data = data.sort_values('open_time')

        rsi = talib.RSI(data['close'].values, timeperiod=self.period)

        data['rsi'] = rsi
        return data[['open_time', 'rsi']]