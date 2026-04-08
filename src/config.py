from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    bot_token: str
    admin_ids: str = ""  # comma-separated

    # 3x-ui panel
    xui_url: str
    xui_path: str
    xui_user: str
    xui_pass: str
    xui_inbound_id: int
    xui_verify_ssl: bool = True

    # VLESS link template
    vless_host: str
    vless_port: int = 443
    vless_pubkey: str
    vless_short_id: str
    vless_sni: str = "www.microsoft.com"
    vless_flow: str = "xtls-rprx-vision"
    vless_fp: str = "chrome"

    # Payments
    payment_mode: str = "manual"  # manual | yookassa
    yookassa_shop_id: str = ""
    yookassa_secret: str = ""
    yookassa_return_url: str = "https://t.me/"
    receipt_email: str = ""
    receipt_description: str = "Доступ к информационному сервису"

    # Storage
    db_path: Path = Field(default=Path("data/bot.db"))

    # Schedulers
    payment_poll_interval: int = 20
    sub_check_interval: int = 10

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x) for x in self.admin_ids.split(",") if x.strip()}

    def is_admin(self, tg_id: int) -> bool:
        return tg_id in self.admin_id_set


settings = Settings()
