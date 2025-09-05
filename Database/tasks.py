import datetime
from decimal import Decimal
import time

from Database.models import PositionManager, Candle, Coin, SideFutures, PlanType, PositionDirection
from ExchangeAPI.APICallManager import Interval, CandleAgent
from celery import shared_task


sl_percentage = 1
tp_percentage = 8

@shared_task
def check_candles_and_open():
    position_manager = PositionManager.objects.get()
    if position_manager.is_position_active:
        return

    agent = CandleAgent(symbol="DOGEUSDT", interval=Interval.HOUR_1)
    new_candles = agent.fetch_future_candles()
    agent.save_to_db(candles=new_candles)

    candles = Candle.objects.filter(
        symbol__symbol="DOGEUSDT",
        interval=Interval.HOUR_1.value[1],
        open_time__gt=position_manager.timestamp_cursor
    ).order_by("-open_time")

    red_count = 0
    red_interrupt = False
    green_count = 0
    green_interrupt = False
    for candle in candles:
        if not candle.is_green():
            red_count += 1
            green_interrupt = True
        elif candle.is_green():
            green_count += 1
            red_interrupt = True

        if red_interrupt and green_interrupt:
            break

        if red_count == 3 or green_count == 3:
            break

    price = position_manager.get_price(coin=Coin.doge_futures.value)
    quantity = Decimal(50 / price)

    if red_count == 3:

        position_manager.futures_trade(
            coin=Coin.doge_futures.value,
            quantity=quantity,
            side=SideFutures.open_short.value
        )


        price = position_manager.get_price(coin=Coin.doge_futures.value)
        sl_price = price * Decimal(1 + sl_percentage / 100)
        tp_price = price * Decimal(1 - tp_percentage / 100)

        time.sleep(0.2)

        print("p" + f'{price}')
        print("sl_price" + f'{Decimal(sl_price)}')
        print("tp_price" + f'{Decimal(tp_price)}')
        position_manager.place_sltp(
            coin=Coin.doge_futures.value,
            plan_type=PlanType.tp.value,
            trigger_price=Decimal(tp_price),
            direction=PositionDirection.short.value,
            quantity=quantity
        )

        time.sleep(0.2)

        remote_id = position_manager.place_sltp(
            coin=Coin.doge_futures.value,
            plan_type=PlanType.sl.value,
            trigger_price=Decimal(sl_price),
            direction=PositionDirection.short.value,
            quantity=quantity
        )

        position_manager.remote_id = remote_id
        position_manager.sl_order_price = Decimal(sl_price)
        position_manager.is_position_active = True
        position_manager.save(update_fields=["remote_id",
                                             "is_position_active",
                                             "sl_order_price",
                                             "updated"])

    elif green_count == 3:
        position_manager.futures_trade(
            coin=Coin.doge_futures.value,
            quantity=quantity,
            side=SideFutures.open_long.value
        )


        price = position_manager.get_price(coin=Coin.doge_futures.value)
        sl_price = price * Decimal(1 - sl_percentage / 100)
        tp_price = price * Decimal(1 + tp_percentage / 100)

        time.sleep(0.2)

        position_manager.place_sltp(
            coin=Coin.doge_futures.value,
            plan_type=PlanType.tp.value,
            trigger_price=Decimal(tp_price),
            direction=PositionDirection.long.value,
            quantity=quantity
        )

        time.sleep(0.2)

        remote_id = position_manager.place_sltp(
            coin=Coin.doge_futures.value,
            plan_type=PlanType.sl.value,
            trigger_price=Decimal(sl_price),
            direction=PositionDirection.long.value,
            quantity=quantity
        )

        position_manager.remote_id = remote_id
        position_manager.sl_order_price = Decimal(sl_price)
        position_manager.is_position_active = True
        position_manager.save(update_fields=["remote_id",
                                             "is_position_active",
                                             "sl_order_price",
                                             "updated"])

@shared_task
def check_position():
    position_manager = PositionManager.objects.get()

    if position_manager.remote_id is None:
        return
    changed = position_manager.modify_sltp(
        coin=Coin.doge_futures.value,
        remote_id=position_manager.remote_id,
        plan_type=PlanType.sl.value,
        trigger_price=position_manager.sl_order_price,
    )
    if changed == "Changed":
        position_manager.is_position_active = False
        position_manager.remote_id = None
        position_manager.timestamp_cursor = datetime.datetime.now().timestamp() * 1000
        position_manager.save(update_fields=["is_position_active",
                                             "remote_id",
                                             "timestamp_cursor",
                                             "updated"])

@shared_task
def my_task():
    check_position()
    time.sleep(0.2)
    check_candles_and_open()
