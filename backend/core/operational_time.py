"""ADR-335：營運時間統一含時區；無時區任務值不能猜測。"""
from datetime import datetime, timezone, timedelta

TAIPEI = timezone(timedelta(hours=8))


def now():
    return datetime.now(timezone.utc)


def parse(value, legacy_timezone=None):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if result.tzinfo is None:
            if legacy_timezone is None:
                return None
            result = result.replace(tzinfo=legacy_timezone)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def iso(value=None):
    return (value or now()).astimezone(timezone.utc).isoformat()


def trustworthy(station):
    """測試舊式 fixture 無 freshness；正式資料只接受 live、合法可營運觀測。"""
    return (station.get('data_freshness') in (None, 'live')
            and station.get('status') in ('empty', 'full', 'low', 'normal', 'high')
            and not station.get('quality_reasons'))
