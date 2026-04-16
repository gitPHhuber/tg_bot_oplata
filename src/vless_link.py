"""Сборка ссылок для клиента:
- build_vless_link: классическая vless:// ссылка из параметров инбаунда + UUID
- build_sub_link: HTTPS-subscription URL для 3x-ui subscription-server
- build_tap_link: one-tap URL для кнопок Telegram (Happ crypt5 API + fallback)
"""
import logging
import time
from urllib.parse import quote

import aiohttp

from .config import settings

log = logging.getLogger(__name__)

_HAPP_API = "https://crypto.happ.su/api-v2.php"
_HAPP_TIMEOUT = 3.0
_CRYPT_TTL = 24 * 3600
_crypt_cache: dict[str, tuple[str, float]] = {}


def build_vless_link(client_uuid: str, remark: str = "VPN") -> str:
    params = (
        f"type=tcp"
        f"&security=reality"
        f"&pbk={settings.vless_pubkey}"
        f"&fp={settings.vless_fp}"
        f"&sni={settings.vless_sni}"
        f"&sid={settings.vless_short_id}"
        f"&spx=%2F"
        f"&flow={settings.vless_flow}"
    )
    return (
        f"vless://{client_uuid}@{settings.vless_host}:{settings.vless_port}"
        f"?{params}#{quote(remark)}"
    )


def build_vless_link_wl(client_uuid: str, remark: str = "Atlas-WL") -> str:
    """VLESS-link для WL-inbound (relay с dest=pimg.mycdn.me).
    Используется когда sub_wl_base_url не задан."""
    params = (
        f"type=tcp"
        f"&security=reality"
        f"&pbk={settings.vless_wl_pubkey}"
        f"&fp={settings.vless_wl_fp}"
        f"&sni={settings.vless_wl_sni}"
        f"&sid={settings.vless_wl_short_id}"
        f"&spx=%2F"
        f"&flow={settings.vless_flow}"
    )
    return (
        f"vless://{client_uuid}@{settings.vless_wl_host}:{settings.vless_wl_port}"
        f"?{params}#{quote(remark)}"
    )


def build_sub_link(sub_id: str, wl: bool = False) -> str:
    """Публичный HTTPS-endpoint подписки (sub_base_url + sub_id).
    wl=True → использует отдельный sub_wl_base_url (subscription-сервер relay-панели).
    Возвращает пустую строку если нужный sub_base_url не настроен или sub_id пустой."""
    base_url = settings.sub_wl_base_url if wl else settings.sub_base_url
    if not base_url or not sub_id:
        return ""
    return f"{base_url.rstrip('/')}/{sub_id}"


def build_happ_deeplink(sub_link: str) -> str:
    """happ://add?url=<urlencoded sub_link> — legacy deeplink для fallback."""
    if not sub_link:
        return ""
    return f"happ://add?url={quote(sub_link, safe='')}"


def build_primary_link(
    sub_id: str, client_uuid: str, remark: str = "Atlas", wl: bool = False
) -> str:
    """Основная ссылка для показа юзеру (fallback-копипаст). HTTPS-sub если
    доступна, иначе классическая vless://.
    wl=True → ссылка для WL-inbound (другой host/port/pbk/sni)."""
    link = build_sub_link(sub_id, wl=wl)
    if link:
        return link
    return build_vless_link_wl(client_uuid, remark=remark) if wl else build_vless_link(client_uuid, remark=remark)


async def _fetch_happ_crypt_link(sub_url: str) -> str | None:
    """POST https://crypto.happ.su/api-v2.php → happ://crypt5/<blob>.
    Результат кэшируется на 24 часа per sub_url, крипто-блоб не меняется
    пока не меняется URL подписки. Возвращает None при любой ошибке —
    caller обязан сделать fallback."""
    now = time.time()
    cached = _crypt_cache.get(sub_url)
    if cached and now - cached[1] < _CRYPT_TTL:
        return cached[0]
    try:
        timeout = aiohttp.ClientTimeout(total=_HAPP_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(_HAPP_API, json={"url": sub_url}) as r:
                if r.status != 200:
                    log.warning("happ crypt api status=%s", r.status)
                    return None
                data = await r.json(content_type=None)
                link = (data or {}).get("encrypted_link") or ""
                if not link.startswith("happ://"):
                    log.warning("happ crypt api bad payload: %r", data)
                    return None
                _crypt_cache[sub_url] = (link, now)
                return link
    except Exception as e:
        log.warning("happ crypt api failed for %s: %s", sub_url, e)
        return None


def _derive_connect_base(sub_tap_base: str, sub_link: str) -> str:
    """Вычисляет URL connect.html (redirector для happ://) того же хоста,
    что sub_tap_base или sub_link."""
    for src in (sub_tap_base, sub_link):
        if src and "://" in src:
            host = src.split("://", 1)[1].split("/", 1)[0]
            if host:
                return f"https://{host}/connect.html"
    return ""


async def build_tap_link(sub_id: str, wl: bool = False) -> str:
    """One-tap URL для inline-кнопки Telegram: тап → Happ открывается →
    подписка импортируется без подтверждений.

    Стратегия (в порядке убывания качества one-tap):
      1) Happ crypt-API → `happ://crypt5/<blob>`, обёрнутый в connect.html?d=…
         (Telegram не принимает happ:// в кнопках, нужна HTTPS-обёртка).
      2) fallback SUB_TAP_BASE_URL=activate.html?sub=<hex>  — наша JS-landing
         которая делает location.href=happ://add?url=sub (2 тапа на iOS).
      3) fallback SUB_TAP_BASE_URL=connect.html?d=happ://add?url=sub  — legacy.
      4) raw sub URL если ничего не настроено (откроет 3x-ui инфо-страницу)."""
    sub = build_sub_link(sub_id, wl=wl)
    if not sub:
        return ""
    base = (settings.sub_tap_base_url or "").strip()

    happ_link = await _fetch_happ_crypt_link(sub)
    if happ_link:
        connect_base = _derive_connect_base(base, sub)
        if connect_base:
            return f"{connect_base}?d={quote(happ_link, safe='')}"

    if not base:
        return sub
    if "activate.html" in base:
        return f"{base}?sub={sub_id}"
    happ = f"happ://add?url={quote(sub, safe='')}"
    return f"{base}?d={quote(happ, safe='')}"
