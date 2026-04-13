# Atlas VPN Bot

Telegram-бот для продажи и управления VPN-подписками. Интегрируется с **3x-ui** панелью (VLESS+Reality), принимает оплату через **ЮKassa** (самозанятый), автоматически выдаёт ключи, отслеживает трафик и управляет жизненным циклом подписок.

**~4 400 строк Python** | **16 коммитов** от MVP до продакшна | **aiogram 3 + aiosqlite + APScheduler**

---

## Возможности

### Для пользователей
- 🛒 **Покупка подписки** — выбор тарифа, оплата через ЮKassa, мгновенная выдача `vless://` ключа
- 🎁 **3 дня бесплатно** — free trial для новых пользователей (один раз)
- 🤝 **Реферальная программа** — пригласи друга → +7 дней за каждого оплатившего
- 🎁 **Подарить другу** — оплатить подписку и отправить ключ другому юзеру
- 🏷 **Промокоды** — скидка % или фиксированная сумма
- 📊 **Профиль** — прогресс-бар трафика, дни до истечения, история подписок
- 📲 **QR-код ключа** — сканируй с телефона для мгновенного подключения
- 📋 **Копирование ключа** — отправка чистым сообщением для лёгкого копирования
- 💬 **Поддержка через бот** — сообщения ретранслируются админу, username не раскрывается
- ℹ️ **О сервисе + договор оферты** — брендовые экраны

### Для администратора
- 🛠 **Inline-панель** (`/admin`) — полное управление через кнопки в Telegram
- 📊 **Статистика** — за день/неделю/месяц/всё время: юзеры, оплаты, выручка, средний чек
- 🖥 **Состояние сервера** — CPU, RAM, диск, uptime, статус Xray, TCP/UDP-соединения
- 👥 **Список юзеров** с пагинацией + поиск по ID или @username
- 🔐 **Список подписок** с реальным трафиком из xray (batch-запрос, без N+1)
- 🎁 **Подарить ключ** — произвольный срок + лимит трафика для любого юзера
- ➕ **Продлить подписку** — +7/14/30/90 дней одной кнопкой
- ❌ **Отозвать подписку** — удаляет клиента из xray
- 📨 **Сообщение юзеру** — DM через бот (username админа не палится)
- 📢 **Рассылка** — preview → подтверждение → прогресс-бар → отчёт
- 🏷 **Управление промокодами** — `/promo create`, `/promo list`

### Автоматика
- ⏰ **Polling платежей** — каждые 20 сек проверяет статус в ЮKassa
- 📅 **Истечение подписок** — уведомление за 24ч (один раз, без спама) + авто-деактивация
- 🔄 **Авто-релогин** — при протухании cookie панели бот сам переавторизуется
- 🛡 **Throttling** — защита от спам-кликов (0.4с на юзера)
- 🔐 **Реферальный бонус** — автоначисление при первой активации приведённого юзера

---

## Стек

| Компонент | Технология |
|---|---|
| Telegram-фреймворк | aiogram 3 (async, FSM, middleware) |
| База данных | SQLite (aiosqlite, WAL mode) |
| VPN-панель | 3x-ui (Xray-core, VLESS+Reality) |
| Платежи | ЮKassa SDK (polling, для самозанятых) |
| Фоновые задачи | APScheduler (async) |
| Конфигурация | pydantic-settings (.env) |
| QR-коды | qrcode + Pillow |
| Деплой | systemd + cron backup |

---

## Структура проекта

```
vpn-bot/
├── README.md
├── .env.example               # шаблон конфигурации
├── .gitignore
├── requirements.txt            # Python-зависимости
│
├── assets/                     # логотипы и аватары
│   ├── avatar-512-flat.png     # аватар для @BotFather (512x512)
│   └── logo-atlas.svg
│
├── deploy/
│   ├── vpn-bot.service         # systemd unit
│   └── backup.sh               # ежедневный бэкап БД
│
└── src/
    ├── main.py                 # точка входа: бот + scheduler + middleware
    ├── config.py               # pydantic-settings из .env
    ├── tariffs.py              # тарифы (единственное место правки цен)
    ├── db.py                   # SQLite: схема, миграции, repo-методы
    ├── xui_client.py           # async-клиент 3x-ui API
    ├── payments.py             # ЮKassa SDK (async обёртка)
    ├── vless_link.py           # сборка vless:// строки
    ├── services.py             # бизнес-логика (activate/deactivate/extend/referral)
    ├── scheduler.py            # фоновые задачи (payment poll, expiry check)
    ├── middlewares.py          # DI + throttling
    ├── keyboards.py            # inline + reply клавиатуры
    ├── messages.py             # 60 текстовых констант (HTML)
    ├── ui.py                   # прогресс-бар, статус-эмодзи, QR, форматирование
    └── handlers/
        ├── __init__.py         # регистрация 7 роутеров
        ├── start.py            # /start, главное меню, trial, howto, about, offer
        ├── buy.py              # покупка: тарифы → промо → оплата → ключ
        ├── profile.py          # профиль с трафиком, историей, QR, копированием
        ├── admin.py            # CLI-команды /stats /grant /revoke /promo
        ├── admin_panel.py      # inline-панель: stats/server/users/subs/extend/gift/broadcast
        ├── support.py          # поддержка через бот (relay admin ↔ user)
        ├── referral.py         # реферальная программа
        └── gift_friend.py      # подарок другу через ЮKassa
```

---

## База данных

6 таблиц, SQLite в WAL-режиме. Миграции идемпотентные через `ALTER TABLE ADD COLUMN`.

| Таблица | Назначение |
|---|---|
| `users` | TG-юзеры: id, username, имя, referrer_id, trial_used |
| `subscriptions` | Подписки: UUID клиента в xray, тариф, сроки, трафик, статус |
| `payments` | Платежи: ЮKassa ID, сумма, статус, промо, получатель (gift) |
| `support_threads` | Маппинг admin_msg_id → user_tg_id для relay-ответов |
| `promocodes` | Промокоды: код, тип (% / фикс.), лимит, срок |
| `promocode_uses` | Журнал использования промо (per-user uniqueness) |

---

## Тарифы

Правятся в одном файле `src/tariffs.py`. Дублирования нет.

| Код | Название | Цена | Срок | Трафик | Пометка |
|---|---|---|---|---|---|
| `m_50` | 1 месяц / 50 GB | 150₽ | 30 дн. | 50 GB | — |
| `m_200` | 1 месяц / 200 GB | 250₽ | 30 дн. | 200 GB | 🔥 ХИТ |
| `m_unl` | 1 месяц / без лимита | 350₽ | 30 дн. | ♾ | — |
| `q_unl` | 3 месяца / без лимита | 900₽ | 90 дн. | ♾ | −14% |
| `y_unl` | 1 год / без лимита | 3000₽ | 365 дн. | ♾ | 💎 −29% |

---

## Быстрый старт

### 1. Локальная разработка

```bash
git clone git@github.com:gitPHhuber/tg_bot_oplata.git vpn-bot
cd vpn-bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполнить BOT_TOKEN, ADMIN_IDS, XUI_* параметры
python -m src.main
```

В режиме `PAYMENT_MODE=manual` ЮKassa не нужна — можно выдавать подписки через `/grant`.

### 2. Деплой на сервер

```bash
# на сервере (где уже стоит 3x-ui)
git clone <repo> /opt/vpn-bot
cd /opt/vpn-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env  # заполнить

# systemd
cp deploy/vpn-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vpn-bot
journalctl -u vpn-bot -f

# бэкап (ежедневно в 4:00)
echo "0 4 * * * /opt/vpn-bot/deploy/backup.sh >> /var/log/vpn-bot-backup.log 2>&1" | crontab -
```

### 3. Регистрация бота

1. @BotFather → `/newbot` → получить **BOT_TOKEN**
2. @userinfobot → `/start` → получить свой **tg_id** → в `ADMIN_IDS`
3. @BotFather → `/setuserpic` → загрузить `assets/avatar-512-flat.png`
4. Команды бота регистрируются автоматически через `set_my_commands` при старте

---

## Конфигурация (.env)

### Обязательные

| Переменная | Описание | Пример |
|---|---|---|
| `BOT_TOKEN` | Токен из @BotFather | `123456:AAAA...` |
| `ADMIN_IDS` | TG ID админов через запятую | `12345678` |
| `XUI_URL` | URL панели 3x-ui (без basePath) | `https://1.2.3.4:60619` |
| `XUI_PATH` | webBasePath панели | `cK9tyS4K24k6gJELDS` |
| `XUI_USER` / `XUI_PASS` | Креды панели | `admin` / `secret` |
| `XUI_INBOUND_ID` | ID инбаунда VLESS-Reality | `1` |
| `VLESS_HOST` | Публичный IP сервера | `152.114.195.76` |
| `VLESS_PUBKEY` | Reality public key | `G255YLL7...` |
| `VLESS_SHORT_ID` | Reality short ID | `50ede7b4...` |

### Опциональные

| Переменная | По умолчанию | Описание |
|---|---|---|
| `XUI_VERIFY_SSL` | `true` | `false` для самоподписанных сертификатов |
| `VLESS_SNI` | `www.microsoft.com` | SNI-маскировка |
| `PAYMENT_MODE` | `manual` | `yookassa` для подключения оплаты |
| `YOOKASSA_SHOP_ID` | — | ID магазина ЮKassa |
| `YOOKASSA_SECRET` | — | Секретный ключ ЮKassa |
| `RECEIPT_DESCRIPTION` | `Доступ к информационному сервису` | Описание в чеке (НЕ писать «VPN») |
| `CHANNEL_URL` | — | URL TG-канала (пустой = кнопка скрыта) |
| `REFERRAL_BONUS_DAYS` | `7` | Дней бонуса за реферала |
| `REFERRAL_ENABLED` | `true` | Вкл/выкл реферальной программы |
| `DB_PATH` | `data/bot.db` | Путь к SQLite |
| `PAYMENT_POLL_INTERVAL` | `20` | Интервал проверки платежей (сек) |
| `SUB_CHECK_INTERVAL` | `10` | Интервал проверки истечения (мин) |

---

## Серверная инфраструктура

Бот рассчитан на работу рядом с 3x-ui на одном сервере.

### Типичный стек сервера

| Компонент | Порт | Назначение |
|---|---|---|
| **SSH** | 2222/tcp | Управление (UFW rate-limit) |
| **3x-ui панель** | 60619/tcp | Веб-интерфейс + API |
| **VLESS+Reality** | 443/tcp | VPN для клиентов (xray-core) |
| **Hysteria2** | 8443/udp | Быстрый UDP-VPN (отдельный сервис) |
| **vpn-bot** | — | Telegram bot (polling, без порта) |
| **fail2ban** | — | Защита SSH от брутфорса |
| **UFW** | — | Файрвол (default deny incoming) |
| **acme.sh** | 80/tcp | Обновление LE-сертификата (shortlived IP) |

### Защита

- SSH на нестандартном порту (2222) с UFW rate-limit
- fail2ban aggressive jail (ban 1h после 5 неудач)
- UFW default deny incoming
- Let's Encrypt для панели (автообновление каждые 5 дней)
- Пароли/токены только в `.env` (chmod 600, в `.gitignore`)
- systemd hardening: `ProtectSystem=strict`, `NoNewPrivileges=true`

---

## Архитектура платежей

```
Юзер → «🛒 Купить» → Тариф → [Промокод?] → ЮKassa redirect
                                                    ↓
                                              Юзер платит
                                                    ↓
                        ┌──────── Scheduler (каждые 20с) ──────┐
                        │  GET payment status                  │
                        │  status == "succeeded"?              │
                        │     → activate_subscription()        │
                        │     → send vless:// key to user      │
                        │     → referral bonus if applicable   │
                        └──────────────────────────────────────┘
```

**Защита от двойной активации:** перед `activate_subscription()` платёж переводится в статус `processing`. Если юзер одновременно нажмёт «Проверить оплату» — он увидит «Платёж уже обработан».

**Email уникальность:** `tg-{tg_id}-{uuid_hex[:8]}` — без serial-счётчика, исключает collision при параллельных создаиях.

---

## Реферальная программа

```
Юзер A → делится ссылкой t.me/AtlasFastBot?start=ref_12345
                                ↓
Юзер B → /start → привязка referrer_id = A
                                ↓
Юзер B → первая покупка/trial/gift
                                ↓
process_referral_after_activation():
  - У A есть активная подписка? → +7 дней (extend)
  - Нет? → новая gift-подписка на 7 дней
  - Уведомление A: «🎉 Бонус за реферала! +7 дней»
```

Триггер вызывается из **4 мест**: ЮKassa polling, кнопка «Проверить», админ grant, админ gift. Идемпотентен — только на первой активации.

---

## Промокоды

**Типы:**
- `percent` — скидка в процентах (1-100%)
- `fixed` — скидка в рублях

**Защита:** per-user uniqueness, max_uses лимит, expires_at, enabled флаг.

**Создание (админ):**
```
/promo create WELCOME percent 20           # -20%, бессрочно, безлимитно
/promo create FIRST50 fixed 50 100 7       # -50₽, max 100 шт, 7 дней
/promo list                                 # все промокоды со статистикой
```

**Применение:** скидка считается при создании платежа в ЮKassa, списание после успешной оплаты.

---

## Миграции БД

SQLite не поддерживает `ALTER TABLE DROP COLUMN`. Все миграции — только `ADD COLUMN`, идемпотентные (проверка через `PRAGMA table_info`). Безопасно применяются при старте бота без downtime.

```python
async def _migrate(self, conn):
    cols = {row[1] for row in await conn.execute("PRAGMA table_info(users)").fetchall()}
    if "referrer_id" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
    if "trial_used" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN trial_used INTEGER DEFAULT 0")
    # ... и т.д.
```

---

## Бэкап

Скрипт `deploy/backup.sh` через `.backup` SQLite (consistent при WAL):

```bash
0 4 * * * /opt/vpn-bot/deploy/backup.sh
```

Бэкапит: БД бота + БД 3x-ui + конфиг Hysteria2. Хранит 14 дней.

---

## Подключение ЮKassa (для самозанятых)

1. Регистрация как самозанятый через приложение «Мой налог»
2. На yookassa.ru: завести магазин со статусом «Самозанятый»
3. Получить `shop_id` и `secret_key` → в `.env`
4. `PAYMENT_MODE=yookassa` → `systemctl restart vpn-bot`

⚠️ **В описании магазина и в `RECEIPT_DESCRIPTION` не указывать «VPN/proxy»** — ЮKassa блокирует такие магазины. Использовать: «Доступ к информационному сервису».

---

## Что НЕ покрывает MVP

- **Webhook от ЮKassa** — используется polling. Для >1000 юзеров переключить на webhook
- **Multi-server** — один инбаунд на одном сервере. Для multi-node → Marzban
- **Telegram Stars** — альтернативная платёжка без юр.лица (отдельная интеграция)
- **Web App** — мини-сайт внутри TG с dashboard (нужен frontend)
- **Cloudflare Workers** — обход whitelist-блокировок через CDN (отдельная настройка)
- **i18n** — мультиязычность (сейчас только русский)
- **Баннеры/картинки** — визуальные карточки в сообщениях

---

## Лицензия

Проект приватный. Репозиторий: `github.com:gitPHhuber/tg_bot_oplata.git`
