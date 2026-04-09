"""UI-хелперы: прогресс-бары, статусные эмодзи, форматирование дней.

Чистые функции без зависимостей — удобно тестировать и переиспользовать.
"""
from datetime import datetime, timezone


def progress_bar(used: int, total: int, width: int = 16) -> str:
    """[████████░░░░░░░░] 47%

    used / total в любых единицах. Если total <= 0 (без лимита) — рисуем
    индикатор бесконечности.
    """
    if total <= 0:
        return "♾  без лимита"
    pct = min(max(used / total, 0.0), 1.0)
    filled = round(pct * width)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct * 100:.0f}%"


def status_emoji_for_days(days_left: float) -> str:
    """🟢 / 🟡 / 🔴 / ⚫ в зависимости от того, сколько осталось."""
    if days_left <= 0:
        return "⚫"
    if days_left < 3:
        return "🔴"
    if days_left < 7:
        return "🟡"
    return "🟢"


def days_left(expires_iso: str) -> float:
    """Сколько целых дней осталось до expires_at (может быть < 0)."""
    dt = datetime.fromisoformat(expires_iso)
    delta = dt - datetime.now(timezone.utc)
    return delta.total_seconds() / 86400


def days_left_str(expires_iso: str) -> str:
    """Человекочитаемое 'осталось 5 дней' / 'истекла N дней назад'."""
    d = days_left(expires_iso)
    if d <= 0:
        return f"истекла {abs(int(d))} дн. назад"
    if d < 1:
        hours = int(d * 24)
        return f"осталось ~{hours} ч"
    return f"осталось {int(d)} дн."


def format_bytes(b: int) -> str:
    """Человекочитаемые байты: KB / MB / GB."""
    if b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{b / (1024 * 1024 * 1024):.2f} GB"


def make_qr_png(data: str) -> bytes:
    """Генерирует PNG QR-кода для произвольной строки. Возвращает bytes для send_photo."""
    import io

    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
