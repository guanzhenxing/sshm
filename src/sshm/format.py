"""展示格式化 — 纯展示逻辑，CLI 与 TUI 共用。"""

from datetime import datetime, timezone


def format_last_connected(ts: str | None) -> str:
    """将 ISO 时间戳格式化为可读的相对时间或短日期。"""
    if not ts:
        return "-"
    try:
        dt = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = (now - dt.replace(tzinfo=timezone.utc)).total_seconds()
        if diff < 60:
            return "just now"
        if diff < 3600:
            return f"{int(diff // 60)}m ago"
        if diff < 86400:
            return f"{int(diff // 3600)}h ago"
        if diff < 604800:
            return f"{int(diff // 86400)}d ago"
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return "-"
