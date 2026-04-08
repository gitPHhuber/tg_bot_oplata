# vpn-bot

Telegram-бот для продажи доступа к VPN, построенному на **3x-ui + VLESS+Reality**.
Создаёт клиентов в панели через её HTTP API, принимает оплату через **ЮKassa**
(самозанятый), отдаёт пользователю готовую `vless://` ссылку.

## Возможности

- 💳 Тарифы с лимитом по дням и трафику (`src/tariffs.py`)
- 🔐 Создание/удаление клиентов в 3x-ui через API, лимиты применяются на стороне xray
- 💰 ЮKassa: создание платежа → polling статуса → авто-выдача ключа
- 👨‍💻 Режим `manual`: запуск без ЮKassa, выдача через `/grant`
- ⏰ Авто-уведомления за 24ч до истечения, авто-блокировка после
- 🛡 Админ-команды: `/stats`, `/grant`, `/revoke`, `/userinfo`
- 📦 SQLite (WAL) — выдержит несколько сотен пользователей без боли
- 🧰 systemd-юнит и backup-скрипт в `deploy/`

## Стек

- Python 3.11+
- aiogram 3 (Telegram)
- aiohttp (запросы к 3x-ui)
- aiosqlite (БД)
- APScheduler (фоновые задачи)
- yookassa (официальный SDK)
- pydantic-settings (конфиг из `.env`)

## Локальная разработка

```bash
cd vpn-bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# отредактируй .env (как минимум BOT_TOKEN и ADMIN_IDS)
python -m src.main
```

В режиме `PAYMENT_MODE=manual` ЮKassa не нужна — можно сразу запускать
бота и выдавать подписки командой `/grant`.

## Структура

```
vpn-bot/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── deploy/
│   ├── vpn-bot.service     # systemd unit для прод-деплоя
│   └── backup.sh           # ежедневный бэкап БД бота + 3x-ui
└── src/
    ├── main.py             # entry, инициализация всего
    ├── config.py           # pydantic-settings (.env → typed)
    ├── tariffs.py          # тарифы — единственное место правки цен
    ├── db.py               # async-обёртка над SQLite
    ├── xui_client.py       # клиент 3x-ui API + helpers
    ├── payments.py         # ЮKassa SDK обёртка
    ├── vless_link.py       # сборка vless:// строки
    ├── services.py         # бизнес-логика (activate / deactivate)
    ├── scheduler.py        # APScheduler задачи
    ├── middlewares.py      # инжект db/xui в handler
    ├── keyboards.py        # inline + reply клавиатуры
    ├── messages.py         # все тексты в одном месте
    └── handlers/
        ├── start.py        # /start, главное меню, как подключиться
        ├── buy.py          # выбор тарифа → создание платежа → ключ
        ├── profile.py      # «моя подписка»
        └── admin.py        # /admin /stats /grant /revoke /userinfo
```

## Конфигурация (`.env`)

| Переменная | Что | Пример |
|---|---|---|
| `BOT_TOKEN` | от @BotFather | `123456:AAAA...` |
| `ADMIN_IDS` | tg_id админов через запятую | `12345678,99999999` |
| `XUI_URL` | URL 3x-ui панели (без `/<basePath>`) | `https://152.114.195.76:60619` |
| `XUI_PATH` | webBasePath из настроек панели | `cK9tyS4K24k6gJELDS` |
| `XUI_USER` / `XUI_PASS` | креды панели | `admin` / `secret` |
| `XUI_INBOUND_ID` | ID инбаунда VLESS-Reality | `1` |
| `XUI_VERIFY_SSL` | `true` если у панели валидный TLS (LE) | `true` |
| `VLESS_HOST`, `VLESS_PORT` | публичный адрес сервера | `152.114.195.76`, `443` |
| `VLESS_PUBKEY`, `VLESS_SHORT_ID` | из инбаунда (Reality keypair, shortId) | — |
| `VLESS_SNI` | маскировочный SNI | `www.microsoft.com` |
| `PAYMENT_MODE` | `manual` или `yookassa` | `manual` |
| `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET` | из ЮKassa личного кабинета | — |
| `YOOKASSA_RETURN_URL` | куда вернуть юзера после оплаты | `https://t.me/your_bot` |
| `RECEIPT_EMAIL` | email клиента в чеке (54-ФЗ) | `client@example.com` |
| `RECEIPT_DESCRIPTION` | описание услуги (НЕ писать «VPN») | `Доступ к информационному сервису` |
| `DB_PATH` | путь к sqlite | `data/bot.db` |
| `PAYMENT_POLL_INTERVAL` | сек, как часто опрашивать ЮKassa | `20` |
| `SUB_CHECK_INTERVAL` | мин, как часто проверять истечение | `10` |

## Где взять параметры VLESS

После создания инбаунда VLESS+Reality в 3x-ui:
1. Открой инбаунд → кнопка QR-код / Info
2. Скопируй из получившейся `vless://...` ссылки:
   - `pbk=` → `VLESS_PUBKEY`
   - `sid=` → `VLESS_SHORT_ID`
   - `sni=` → `VLESS_SNI`
3. `XUI_INBOUND_ID` — это колонка ID в таблице инбаундов

## Деплой на сервер

На сервере (где уже стоит 3x-ui):

```bash
# 1. Клонируем
git clone <repo> /opt/vpn-bot
cd /opt/vpn-bot

# 2. venv + зависимости
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Конфиг
cp .env.example .env
nano .env  # заполнить

# 4. Systemd
cp deploy/vpn-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vpn-bot
systemctl status vpn-bot
journalctl -u vpn-bot -f   # смотрим логи

# 5. Бэкап в cron
echo "0 4 * * * /opt/vpn-bot/deploy/backup.sh >> /var/log/vpn-bot-backup.log 2>&1" | crontab -
```

## Тарифы (правка)

Цены/лимиты — только в `src/tariffs.py`. Перезапусти бот после правки:
```bash
systemctl restart vpn-bot
```

## Подключение ЮKassa (для самозанятых)

1. Регистрация СЗ через приложение «Мой налог» (5 минут, паспорт + ИНН)
2. На yookassa.ru: завести магазин со статусом «Самозанятый»
3. Получить `shop_id` и `secret_key` → внести в `.env`
4. `PAYMENT_MODE=yookassa` → `systemctl restart vpn-bot`

⚠️ В описании магазина и в `RECEIPT_DESCRIPTION` **не указывай VPN/proxy** —
ЮKassa блокирует такие магазины. Используй нейтральные формулировки:
«Доступ к информационному сервису», «Подписка на IT-сервис».

## Безопасность

- БД бота лежит в `data/bot.db`, в `.gitignore`
- `.env` тоже в `.gitignore` — никогда не коммить
- Все `xui_uuid` — UUID v4, никаких паттернов
- API панели вызывается через cookie-сессию, авто-релогин при 401
- `getClientTraffic` отдаёт реальные счётчики, можно делать честные «использовано: X GB»

## Что НЕ покрывает MVP

- Webhook от ЮKassa — используется polling. Для большой нагрузки можно
  переключить на webhook (нужен публичный URL с TLS).
- Multi-server — один инбаунд на одном сервере. Для multi-node нужен
  Marzban.
- Промокоды и рефералки — задел в БД есть, добавлять в отдельной итерации.
- Telegram Stars и CryptoBot как альтернативные шлюзы — добавить как
  ещё одну стратегию в `payments.py`.
