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
    # Отдельный inbound для Pro-тарифов со split-tunnel (РФ-домены идут
    # direct outbound на relay, минуя exit). 0 = не настроен, Pro-клиенты
    # будут создаваться в основном inbound (без split-tunnel).
    xui_inbound_id_pro: int = 0
    xui_verify_ssl: bool = True

    # ----- Whitelist-bypass inbound (отдельная 3x-ui панель на relay) -----
    # Тариф «🛡 Обход белых списков» создаёт клиентов в этом inbound'е.
    # Пусто → тариф недоступен, кнопка не показывается.
    # Reality dest=pimg.mycdn.me (CDN Одноклассников в белом списке ТСПУ).
    xui_wl_url: str = ""
    xui_wl_path: str = ""
    xui_wl_user: str = ""
    xui_wl_pass: str = ""
    xui_wl_inbound_id: int = 0
    xui_wl_verify_ssl: bool = False

    # VLESS link template
    vless_host: str
    vless_port: int = 443
    # Порт Pro-inbound на relay (split-tunnel). 0 = используем vless_port.
    # Нужен только для fallback-VLESS link; в subscription-URL 3x-ui сам
    # подставляет правильный порт по inbound клиента.
    vless_port_pro: int = 0
    vless_pubkey: str
    vless_short_id: str
    vless_sni: str = "www.microsoft.com"
    vless_flow: str = "xtls-rprx-vision"
    vless_fp: str = "chrome"

    # ----- VLESS link для WL-тарифа (собирается когда нет sub-сервера) -----
    vless_wl_host: str = ""
    vless_wl_port: int = 8447
    vless_wl_pubkey: str = ""
    vless_wl_short_id: str = ""
    vless_wl_sni: str = "pimg.mycdn.me"
    vless_wl_fp: str = "ios"

    # Публичный subscription-endpoint для WL-клиентов (если sub-сервер на
    # relay-панели поднят отдельно). Пусто → будет выдаваться raw vless://.
    sub_wl_base_url: str = ""

    @property
    def wl_configured(self) -> bool:
        """True если WL-inbound полностью настроен и тариф можно продавать."""
        return bool(
            self.xui_wl_url and self.xui_wl_path and self.xui_wl_user
            and self.xui_wl_pass and self.xui_wl_inbound_id
            and self.vless_wl_host and self.vless_wl_pubkey
            and self.vless_wl_short_id
        )

    # Публичный endpoint 3x-ui subscription-server (e.g. https://176-108-242-105.nip.io/sub/).
    # Если задан — бот выдаёт клиенту https-подписку + Happ-deeplink.
    # Если пуст — fallback на классический vless:// (без one-tap Happ).
    sub_base_url: str = ""

    # HTTPS-landing для one-tap открытия в Happ из Telegram-кнопки
    # (connect.html на relay, принимает ?d=<url-encoded-happ-link>, делает JS-редирект).
    # Если пуст — кнопка «Активировать профиль» ведёт прямо на sub-URL
    # (откроет 3x-ui инфо-страницу в браузере, а не Happ).
    sub_tap_base_url: str = ""

    # Payments
    payment_mode: str = "manual"  # manual | yookassa
    yookassa_shop_id: str = ""
    yookassa_secret: str = ""
    yookassa_return_url: str = "https://t.me/"
    receipt_email: str = ""
    receipt_description: str = "Доступ к информационному сервису"

    # Brand / контент главного меню
    channel_url: str = ""           # пустой → кнопка «Наш канал» скрыта
    about_text: str = (
        "<b>Atlas</b> — информационный сервис, обеспечивающий стабильный и "
        "быстрый доступ к сети для работы, учёбы и развлечений.\n\n"
        "🔥 <b>Что даёт Atlas?</b>\n\n"
        "• Стабильная скорость соединения без искусственных ограничений\n"
        "• Современные протоколы передачи данных с шифрованием\n"
        "• Подключение до 10 устройств с одной подписки\n"
        "• Работает на смартфоне, ноутбуке, планшете и телевизоре\n"
        "• Круглосуточная поддержка в чате\n\n"
        "Atlas обеспечивает безопасное и стабильное соединение для работы и "
        "развлечений — где бы вы ни находились. 🚀"
    )
    # Если указан offer_url — кнопка «📄 Договор оферты» ведёт туда (teletype
    # и т.п.), offer_text ниже не показывается. Если пусто — fallback на текст
    # из бота (устаревший вариант).
    offer_url: str = ""
    offer_text: str = (
        "<b>Договор-оферта на оказание услуг</b>\n\n"
        "Настоящий документ является публичной офертой (далее — «Оферта») и "
        "содержит существенные условия договора на оказание услуг доступа к "
        "информационному сервису Atlas (далее — «Сервис»).\n\n"
        "<b>1. Предмет оферты</b>\n"
        "Исполнитель предоставляет Пользователю на возмездной основе доступ к "
        "информационному сервису по выбранному тарифу. Перечень тарифов "
        "доступен в боте в разделе «🛒 Купить подписку».\n\n"
        "<b>2. Стоимость и порядок оплаты</b>\n"
        "Стоимость услуг указана в рублях РФ и доступна в момент покупки. "
        "Оплата производится через сервис ЮKassa (для самозанятых) или иной "
        "указанный платёжный шлюз. Услуга считается оплаченной с момента "
        "поступления средств Исполнителю.\n\n"
        "<b>3. Сроки и порядок оказания услуг</b>\n"
        "Услуга предоставляется на срок, указанный в выбранном тарифе. "
        "Доступ активируется автоматически в течение нескольких минут после "
        "получения оплаты.\n\n"
        "<b>4. Возврат средств</b>\n"
        "Возврат осуществляется в случае технической невозможности оказать "
        "услугу по вине Исполнителя. Заявка на возврат — через бот, раздел "
        "«🆘 Помощь».\n\n"
        "<b>5. Ответственность</b>\n"
        "Пользователь самостоятельно несёт ответственность за соблюдение "
        "законодательства при использовании Сервиса. Исполнитель не "
        "обрабатывает и не хранит передаваемый трафик.\n\n"
        "<b>6. Реквизиты</b>\n"
        "Уточняются у Исполнителя по запросу через раздел «🆘 Помощь».\n\n"
        "<i>Совершая оплату, Пользователь принимает условия настоящей оферты "
        "в полном объёме.</i>"
    )

    # Реферальная программа
    referral_bonus_days: int = 7    # сколько дней дарим реферреру за каждого оплатившего реферала
    referral_enabled: bool = True

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
