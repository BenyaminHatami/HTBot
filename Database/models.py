from django.db import models
from decimal import Decimal
from enum import Enum
from django.db import models
import requests
import time
import hmac
import base64

from .utils import get_param, interpret_response

class Symbol(models.Model):
    symbol = models.CharField(max_length=50, primary_key=True)

    class Meta:
        db_table = 'symbols'

    def __str__(self):
        return self.symbol

class CandleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().order_by('open_time')

class Candle(models.Model):
    open_time = models.BigIntegerField()
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE)
    interval = models.BigIntegerField()
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    base_volume = models.FloatField()
    usdt_volume = models.FloatField()
    quote_volume = models.FloatField()

    objects = CandleManager()

    unordered_objects = models.Manager()

    class Meta:
        db_table = 'candles'
        unique_together = (('open_time', 'symbol', 'interval'),)
        ordering = ['-open_time']

    def __str__(self):
        return f"{self.symbol} - {self.open_time}"


    def is_green(self):
        return self.open - self.close <= 0


class Coin(Enum):
    type = str
    btc_spot = "BTCUSDT_SPBL"
    btc_futures = "BTCUSDT_UMCBL"
    doge_futures = "DOGEUSDT_UMCBL"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class PositionDirection(Enum):
    type = str
    long = "long"
    short = "short"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class SideFutures(Enum):
    type = str
    open_long = "open_long"
    close_long = "close_long"
    open_short = "open_short"
    close_short = "close_short"
    unknown = "unknown"

    @staticmethod
    def get_position_direction(side):
        if side == SideFutures.open_long.value:
            return PositionDirection.long.value
        elif side == SideFutures.open_short.value:
            return PositionDirection.short.value

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class PlanType(Enum):
    type = str
    tp = "profit_plan"
    sl = "loss_plan"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class State(Enum):
    type = int
    Active = 1
    Inactive = 2
    Pending = 3

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class BaseModel(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    trace = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True


class PositionManager(BaseModel):
    api_key = models.CharField(max_length=1000)
    secret_key = models.CharField(max_length=1000)
    api_passphrase = models.CharField(max_length=1000)
    timestamp_cursor = models.BigIntegerField(default=100)
    is_position_active = models.BooleanField(default=False)
    remote_id = models.CharField(max_length=2000, null=True, blank=True)
    sl_order_price = models.DecimalField(decimal_places=10, max_digits=20, null=True, blank=True)


    def sign(self, message, secret_key):
        mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
        d = mac.digest()
        return base64.b64encode(d)

    def pre_hash(self, timestamp, method, request_path, body=None, query_string=None):
        if query_string is None:
            return str(timestamp) + str.upper(method) + request_path + body
        else:
            return str(timestamp) + str.upper(method) + request_path + "?" + query_string

    def create_signature(self, timestamp, method, request_path, body=None, query_string=None):
        message = self.pre_hash(timestamp=str(timestamp), method=method, request_path=request_path, body=body,
                                query_string=query_string)
        signature_b64 = self.sign(message, self.secret_key)
        return signature_b64

    def create_header(self, method, request_path, body=None, query_string=None):
        timestamp = int(time.time_ns() / 1000000)
        signature_b64 = self.create_signature(timestamp=str(timestamp),
                                              method=method,
                                              request_path=request_path,
                                              body=body,
                                              query_string=query_string)
        headers = {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature_b64,
            'ACCESS-TIMESTAMP': str(timestamp),
            'ACCESS-PASSPHRASE': self.api_passphrase,
            'Content-Type': 'application/json',
            'locale': 'en-US'
        }
        return headers


    def futures_trade(self, coin: Coin.type, quantity: Decimal, side: SideFutures.type):
        method = "POST"
        request_path = "/api/mix/v1/order/placeOrder"
        body = (f'{{"side":"{side}",'
                f'"symbol":"{coin}",'
                f'"orderType":"market",'
                f'"marginCoin":"USDT",'
                f'"size":"{quantity}"}}')

        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/order/placeOrder",
                                 data=body,
                                 headers=headers)
        remote_id = interpret_response(response.json(), "orderId")
        print(response.text)
        return remote_id


    def place_sltp(self, coin: Coin.type,
                   plan_type: PlanType.type,
                   trigger_price: Decimal,
                   direction: PositionDirection.type,
                   quantity: Decimal):
        method = "POST"
        request_path = "/api/mix/v1/plan/placeTPSL"
        body = (f'{{"symbol":"{coin}",'
                f'"marginCoin":"USDT",'
                f'"planType":"{plan_type}",'
                f'"triggerPrice":"{round(trigger_price, 6)}",'
                f'"holdSide":"{direction}"}}')
        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/plan/placeTPSL",
                                 data=body,
                                 headers=headers)
        print(response.text)
        remote_id = interpret_response(response.json(), "orderId")
        return remote_id


    def modify_sltp(
            self,
            coin: Coin.type,
            plan_type: PlanType.type,
            remote_id: str,
            trigger_price: Decimal
    ):
        method = "POST"
        request_path = "/api/mix/v1/plan/modifyTPSLPlan"
        body = (f'{{"symbol":"{coin}",'
                f'"marginCoin":"USDT",'
                f'"planType":"{plan_type}",'
                f'"triggerPrice":"{round(trigger_price, 6)}",'
                f'"orderId":"{remote_id}"}}')
        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/plan/modifyTPSLPlan",
                                 data=body,
                                 headers=headers)
        print(response.text)
        response_code = response.json().get('code', None)
        print(f"response_code is {response_code}")
        if response.status_code == 200:
            if response_code == '00000':
                return True
        else:
            if response_code == '43020':
                return "Changed"
            return False


    def cancel_sltp(self, sltporder):
        method = "POST"
        request_path = "/api/mix/v1/plan/cancelPlan"
        body = (f'{{"symbol":"{sltporder.coin}",'
                f'"marginCoin":"USDT",'
                f'"planType":"{sltporder.plan_type}",'
                f'"orderId":"{sltporder.remote_id}"}}')
        headers = self.create_header(method=method, request_path=request_path, body=body)
        response = requests.post(url="https://api.coincatch.com/api/mix/v1/plan/cancelPlan",
                                 data=body,
                                 headers=headers)
        print(response.text)
        if response.status_code == 200:
            return True
        else:
            return False


    def get_price(self, coin: Coin.type):
        method = "GET"
        request_path = "/api/mix/v1/market/mark-price"
        query_string = f'symbol={coin}'
        headers = self.create_header(method=method, request_path=request_path, query_string=query_string)
        response = requests.get(url="https://api.coincatch.com/api/mix/v1/market/mark-price" + "?" + query_string,
                                headers=headers)
        print(response.text)
        if response.status_code != 200:
            raise Exception("Error in get price!")
        return Decimal(response.json().get('data').get('markPrice'))


    def get_order_detail(self, coin: Coin.type, remote_id: str):
        method = "GET"
        request_path = "/api/mix/v1/order/detail"
        query_string = f'symbol={coin}&orderId={remote_id}'
        headers = self.create_header(method=method, request_path=request_path, query_string=query_string)
        response = requests.get(url="https://api.coincatch.com/api/mix/v1/order/detail" + "?" + query_string,
                                headers=headers)
        print(response.json())


    def get_position_order_information(self, coin: Coin.type, remote_id: str):
        method = "GET"
        request_path = "/api/mix/v1/order/fills"
        query_string = f'symbol={coin}&orderId={remote_id}'
        headers = self.create_header(method=method, request_path=request_path, query_string=query_string)
        response = requests.get(url="https://api.coincatch.com/api/mix/v1/order/fills" + "?" + query_string,
                                headers=headers)
        print(response.json())
        try:
            data = interpret_response(dictionary=response.json())[0]
        except IndexError:
            raise Exception("No order found")
        output = {
            "price": get_param(data, "price"),
            "quantity": get_param(data, "sizeQty"),
            "fee": get_param(data, "fee"),
            "fill_amount": get_param(data, "fillAmount"),
            "profit": get_param(data, "profit"),
            "side": get_param(data, "side"),
            "created": get_param(data, "cTime"),
        }
        return output

    def get_sltp_order_information(self, coin: Coin.type, remote_id: str):
        method = "GET"
        request_path = "/api/mix/v1/order/detail"
        query_string = f'symbol={coin}&orderId={remote_id}'
        headers = self.create_header(method=method, request_path=request_path, query_string=query_string)
        response = requests.get(url="https://api.coincatch.com/api/mix/v1/order/detail" + "?" + query_string,
                                headers=headers)
        print(response.json())

