"""寄送排程：每人每天上限、每分鐘限速（F-MAIL-6、SPEC 7.5）。

「一天」以台灣時間計算；超過上限的排到隔天上班時間。純 Python。
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")


def local_day(at: datetime, tz: ZoneInfo = TAIPEI) -> date:
    return at.astimezone(tz).date()


def day_bounds(day: date, tz: ZoneInfo = TAIPEI) -> tuple[datetime, datetime]:
    """這一天（當地時間）的起訖，回傳 UTC 可比較的 aware datetime。"""
    start = datetime.combine(day, time(0), tzinfo=tz)
    return start, start + timedelta(days=1)


def next_day_start(at: datetime, day_start_hour: int, tz: ZoneInfo = TAIPEI) -> datetime:
    """隔天上班時間（當地時間 day_start_hour 點）。"""
    tomorrow = local_day(at, tz) + timedelta(days=1)
    return datetime.combine(tomorrow, time(day_start_hour), tzinfo=tz)


def plan_send_times(
    n: int,
    *,
    start: datetime,
    already_today: int,
    daily_limit: int,
    per_minute: int,
    day_start_hour: int = 9,
    tz: ZoneInfo = TAIPEI,
) -> list[datetime]:
    """排出 n 封信的寄送時間。

    already_today：寄件人在 start 那一天（當地時間）已經寄出或已排定的封數。
    同一天超過 daily_limit 就排到隔天 day_start_hour 點；每封間隔 60 / per_minute 秒。
    """
    if daily_limit < 1 or per_minute < 1:
        raise ValueError("daily_limit 與 per_minute 必須大於 0")
    gap = timedelta(seconds=60 / per_minute)
    times: list[datetime] = []
    cursor = start
    day = local_day(cursor, tz)
    count = already_today
    for _ in range(n):
        if local_day(cursor, tz) != day:  # 跨過午夜，新的一天重新計數
            day = local_day(cursor, tz)
            count = 0
        if count >= daily_limit:
            cursor = next_day_start(cursor, day_start_hour, tz)
            day = local_day(cursor, tz)
            count = 0
        times.append(cursor)
        count += 1
        cursor = cursor + gap
    return times
