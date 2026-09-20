"""Pure parsers for current-cycle daily data and today's hourly data."""
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def usage_value(value):
    if isinstance(value, bool):
        raise ValueError("用电量不能为布尔值")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("用电量必须为非负有限数值")
    return number


def values(data):
    columns = data.get("columns")
    if not isinstance(columns, list) or not columns or not columns[0]:
        raise ValueError("图表缺少用电量列")
    return columns[0][1:]


def parse_daily(data, reference_date=None):
    """Resolve populated current-cycle month/day labels to the latest past date.

    This parser is intentionally scoped to the current billing cycle; archived
    billing periods must supply their own reference_date.
    """
    now = datetime.now(JST)
    reference = reference_date or now.date()
    labels = data.get("shiyoKikan")
    readings = values(data)
    if not isinstance(labels, list) or len(labels) - 1 != len(readings):
        raise ValueError("日期与用电量列长度不一致")
    rows, seen = [], set()
    for label, reading in zip(labels[1:], readings):
        if reading is None:
            continue
        month, day = map(int, label.split("/"))
        candidates = []
        for year in (reference.year, reference.year - 1):
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if candidate <= reference:
                candidates.append(candidate)
        if not candidates:
            raise ValueError("无效日期")
        parsed = max(candidates)
        if (reference - parsed).days > 62 or parsed in seen:
            raise ValueError("日期超出当前计费周期范围或重复")
        seen.add(parsed)
        rows.append(dict(date=parsed, date_str=label,
                         usage_kwh=usage_value(reading), timestamp=now))
    return rows


def parse_hourly(data, target_date=None):
    now = datetime.now(JST)
    target = target_date or now.date()
    readings = values(data)
    if len(readings) > 24:
        raise ValueError("小时图表超过 24 个时段")
    return [dict(date=target, date_str=target.isoformat(), hour=hour,
                 usage_kwh=usage_value(value), timestamp=now)
            for hour, value in enumerate(readings) if value is not None]
