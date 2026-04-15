"""Сборка ссылок для клиента:
- build_vless_link: классическая vless:// ссылка из параметров инбаунда + UUID
- build_sub_link: HTTPS-subscription URL для 3x-ui subscription-server (если настроен)
- build_happ_deeplink: одноклик `happ://add?url=<sub>` для авто-импорта в Happ
"""
from urllib.parse import quote

from .config import settings


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


def build_sub_link(sub_id: str) -> str:
    """Публичный HTTPS-endpoint подписки (sub_base_url + sub_id).
    Возвращает пустую строку если sub_base_url не настроен или sub_id пустой
    (например legacy-подписки до миграции sub_id)."""
    if not settings.sub_base_url or not sub_id:
        return ""
    base = settings.sub_base_url.rstrip("/")
    return f"{base}/{sub_id}"


def build_happ_deeplink(sub_link: str) -> str:
    """happ://add?url=<urlencoded sub_link> — auto-import в Happ одним тапом."""
    if not sub_link:
        return ""
    return f"happ://add?url={quote(sub_link, safe='')}"


def build_primary_link(sub_id: str, client_uuid: str, remark: str = "Atlas") -> str:
    """Основная ссылка, которую мы показываем юзеру. HTTPS-sub если доступна
    (one-tap через Happ), иначе — классическая vless://."""
    link = build_sub_link(sub_id)
    return link or build_vless_link(client_uuid, remark=remark)
