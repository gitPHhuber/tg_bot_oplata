"""Сборка vless:// ссылки из параметров инбаунда + UUID клиента."""
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
