# Diary API — full setup guide

REST API + sync container for a Custom GPT diary system. Stores your entries in SQLite and mirrors them as Markdown files into a private GitHub repo (Obsidian-friendly).

## What you're building

```
ChatGPT Custom GPT
    │  HTTPS
    ▼
ngrok tunnel (https://YOUR-DOMAIN.ngrok-free.dev)
    │
    ▼
FastAPI (diary-api, port 8000)
    │
    ▼
SQLite (data/diary.db)
    ▲
    │ read-only every 60s
    │
diary-sync container
    │
    ▼ push only the entries whose hash changed
    │
GitHub: yourname/diary-vault (private, Obsidian-friendly)
```

Three Docker containers run side by side:

| Container | What it does |
|---|---|
| `diary-api` | FastAPI on port 8000 — `/stats`, `/entries/summary`, `/entries/{id}`, `POST /entries`. |
| `diary-ngrok` | Public HTTPS tunnel to `diary-api`, so the Custom GPT can reach it. |
| `diary-sync` | Reads the SQLite DB, renders each entry as `.md`, pushes changed files to a GitHub repo via the Contents API. |

## Prerequisites

- **Docker + docker-compose** (Docker Desktop on Mac/Win, or `apt install docker.io docker-compose-plugin` on Linux).
- **ngrok account** (free tier is enough) — sign up at https://ngrok.com, grab an authtoken, claim a static domain in [Domains](https://dashboard.ngrok.com/domains).
- **ChatGPT Plus subscription** ($20/mo) — Custom GPTs are a Plus feature.
- **GitHub account** + a **private repo** to use as the vault (e.g. `yourname/diary-vault`, empty is fine).
- **GitHub fine-grained PAT** with `Contents: Read and write` on that one repo only.

### Choose your server

Anything that runs Docker 24/7. The API is tiny (~50 MB RAM).

| Option | Cost | Good for |
|---|---|---|
| Raspberry Pi 4/5 at home | one-time hardware | privacy-first, electricity is cheap |
| Small VPS (Hetzner CX11, DO $5, Oracle ARM free) | $0–5/mo | no home network worries, reachable from anywhere |
| Old laptop / mini PC running 24/7 | $0 | quickest if you already own one |

All three are interchangeable — the only difference is where you SSH and where the files live. Pick what you have.

## Step-by-step install

### 1. Prepare GitHub vault repo

1. Go to https://github.com/new and create a **private** repo, e.g. `diary-vault`. Initialize it with a README so the default branch exists.
2. Go to https://github.com/settings/personal-access-tokens/new and create a **fine-grained PAT**:
   - **Resource owner:** your user
   - **Repository access:** Only select repositories → pick `diary-vault`
   - **Permissions:** Repository permissions → **Contents: Read and write**
   - Save the token — you'll paste it as `GITHUB_DIARY_TOKEN`.

### 2. Prepare ngrok

1. Sign up at https://ngrok.com.
2. Copy the authtoken from https://dashboard.ngrok.com/get-started/your-authtoken.
3. Reserve a static domain at https://dashboard.ngrok.com/domains → "New Domain" → free format `something-random.ngrok-free.dev`. Without this, the URL changes on every restart and the Custom GPT breaks.

### 3. Clone and configure

```bash
git clone git@github.com:YOUR-USERNAME/diary-gpt.git
cd diary-gpt/diary_api

cp .env.example .env
# Edit .env — see table below
```

`.env` reference:

| Variable | Required | What |
|---|---|---|
| `DIARY_API_KEY` | yes | API auth key. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `DB_PATH` | no | SQLite path inside the container (default `data/diary.db`). |
| `NGROK_AUTHTOKEN` | yes | From the ngrok dashboard. |
| `NGROK_DOMAIN` | yes | Your reserved domain, e.g. `purple-finch-123.ngrok-free.dev` (no `https://`). |
| `GITHUB_DIARY_TOKEN` | yes (for sync) | Fine-grained PAT with Contents R+W on the vault repo. |
| `VAULT_REPO` | yes (for sync) | `username/diary-vault` — your private repo. |
| `VAULT_SYNC_INTERVAL` | no | Seconds between sync passes (default `60`). |

### 4. Boot

```bash
sudo docker compose up -d

# verify all three containers are up
sudo docker ps | grep diary

# verify the API is reachable through ngrok
curl https://YOUR-DOMAIN.ngrok-free.dev/health
# → {"status":"ok"}
```

### 5. Wire up the Custom GPT in ChatGPT

1. https://chatgpt.com → **Explore GPTs** → **Create** → **Configure**.
2. **Name:** anything (e.g. "Diary").
3. **Instructions:** paste the full block from the [Instructions](#3-instructions) section below.
4. **Actions** → **Create new action**:
   - **Authentication:** API Key → Auth Type: Custom → Custom Header Name: `X-API-Key` → API Key value: your `DIARY_API_KEY`.
   - **Schema:** paste the contents of [openapi.yaml](openapi.yaml). Replace the `servers` URL with your ngrok domain (the file ships with `YOUR-DOMAIN.ngrok-free.dev` — change once).
5. **Publish:** *Only me*.

Test it: send the GPT a short diary entry. After it replies, run:
```bash
sudo sqlite3 ~/diary-gpt/diary_api/data/diary.db \
  "SELECT id, summary, tags FROM diary_entries ORDER BY id DESC LIMIT 1"
```
You should see the entry, and within ~60s it should appear as `diary/{date}_{id}.md` in your GitHub vault repo.

## API эндпоинты

Все эндпоинты кроме `/health` требуют заголовок `X-API-Key`. Полная спецификация в [openapi.yaml](openapi.yaml).

### GET /health

Проверка работоспособности. Без аутентификации.

```bash
curl https://YOUR-DOMAIN.ngrok-free.dev/health
# {"status":"ok"}
```

### GET /stats

Обзор: общее количество записей, диапазон дат, частота тегов. Используется GPT для понимания "ландшафта" перед retrieval.

```bash
curl -H "X-API-Key: YOUR_KEY" https://YOUR-DOMAIN.ngrok-free.dev/stats
```

### GET /entries/summary

Постраничные summaries (50 записей на страницу). Каждая запись: `id`, `created_at`, `summary` (1-2 предложения), `tags`. Полного текста нет — используется для отбора релевантных по тегам.

```bash
curl -H "X-API-Key: YOUR_KEY" \
     "https://YOUR-DOMAIN.ngrok-free.dev/entries/summary?tag=dating&page=1"
```

### GET /entries/{id}

Полный текст конкретной записи.

```bash
curl -H "X-API-Key: YOUR_KEY" https://YOUR-DOMAIN.ngrok-free.dev/entries/191
```

Ответ:
```json
{
  "id": 191,
  "created_at": "2026-05-07T20:35:56.825136+00:00",
  "voice_text": "Полный текст записи...",
  "summary": "Обобщение из voice_text которое делает ChatGPT",
  "tags": "memory,reflection"
}
```

### GET /entries

Полные записи (полный текст), с опциональной фильтрацией по тегу и пагинацией.

```bash
curl -H "X-API-Key: YOUR_KEY" \
     "https://YOUR-DOMAIN.ngrok-free.dev/entries?tag=memory&limit=5"
```

### POST /entries

Создать новую запись. Все три поля обязательны.

```bash
curl -X POST \
     -H "X-API-Key: YOUR_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "voice_text": "Полный текст записи (голосовая транскрипция)",
       "summary": "Обобщение voice_text",
       "tags": "yourtag"
     }' \
     https://YOUR-DOMAIN.ngrok-free.dev/entries
```

## Operational details

### Containers

| Контейнер | Описание |
|---|---|
| `diary-api` | FastAPI сервер на порту 8000 |
| `diary-ngrok` | ngrok туннель → diary-api:8000 |
| `diary-sync` | Цикл sync БД → GitHub vault (Obsidian-friendly `.md`) |

### Логи

```bash
sudo docker logs diary-api --tail 20
sudo docker logs diary-ngrok --tail 20
sudo docker logs diary-sync --tail 20
```

### Vault sync (diary-sync)

Каждые `VAULT_SYNC_INTERVAL` секунд контейнер:
1. Читает БД (mount read-only).
2. Рендерит каждую запись в `.md` (YAML frontmatter + summary блок + voice_text + `#hashtags`).
3. Считает sha256, сравнивает с `/app/state/vault_sync_state.json`.
4. Пушит изменённые через GitHub Contents API (по одному коммиту на запись).

Reset state (заставить пересинхронить всё):
```bash
ssh user@your-server "sudo rm /path/to/diary_api/sync_state/vault_sync_state.json && sudo docker restart diary-sync"
```

Bulk export локально (для первичного push или восстановления):
```bash
python3 sync/sync_vault.py --db-path /tmp/diary.db export \
    --out ~/diary-vault --state /tmp/vault_sync_state.json
```

## Alternative: Obsidian-only (no database)

If you don't want to run a database at all and only need the Obsidian vault, you can drop SQLite entirely.

What changes:
- `POST /entries` writes a `.md` file directly to a mounted vault folder instead of inserting into SQLite. The same hash-tracking logic moves into the API write path.
- `GET /entries/*` parses the vault folder on disk (or reads via the Obsidian [Local REST API plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) if Obsidian itself is running on the server).
- `diary-sync` is no longer needed — `git commit && git push` from a cron inside the vault folder replaces it (or use a `git auto-commit` plugin in Obsidian).

Trade-offs to be aware of:
- **Querying by tag becomes slower** — you parse frontmatter + hashtags from N files on every request instead of `WHERE tags LIKE '%X%'` in SQLite. Fine up to ~1000 entries on a Pi; reconsider above that.
- **No `summary` index** — you still keep summaries in YAML frontmatter, you just lose a single-column index. In practice it doesn't matter at hand-written diary scale.
- **History is git-native** — every entry edit becomes a git commit. Cleaner audit trail at the cost of more commits.

Skeleton of the change (not included here, sketch only):
1. In [api.py](api.py) replace `_get_db()` with a vault-folder helper that parses `.md` files into the same `EntryFull` dict shape.
2. `POST /entries` writes `vault/diary/{YYYY-MM-DD}_{id}.md` with frontmatter and hashtags (use the rendering function from [sync/sync_vault.py](sync/sync_vault.py)).
3. Remove the `diary-sync` service from `docker-compose.yml`. Mount the vault path read-write into `diary-api` instead.
4. Add a tiny cron or a sidecar to `git add -A && git commit -m 'sync' && git push` from the vault every few minutes (or do it inline at the end of `POST /entries`).

This is **not** wired up in this repo by default — `diary-api` writes to SQLite, `diary-sync` mirrors to GitHub. The DB path is the path of least resistance for tag-filtering. The Obsidian-only path is documented here as a viable alternative for those who want zero database.

## Настройка ChatGPT Custom GPT

### 1. Создать GPT

Зайди на https://chatgpt.com → Explore GPTs → Create → Configure

### 2. Name

```
Дневник
```

### 3. Instructions

```
Ты психотерапевт и работаешь в проекте-дневнике. Ищешь причины и паттерны в поведении пользователя, скрытые смыслы, эмоции. Работаешь как настоящий терапевт: строишь гипотезы, проверяешь их уточняющими вопросами, не валидируешь автоматически.

## Важно про источник текста

Сообщения пользователя и записи в БД — это автоматическая транскрипция голосовых заметок. Возможны ошибки распознавания: неправильные слова, обрывки фраз, путаница омонимов, имена с искажениями. Если слово в контексте звучит странно или не складывается со смыслом — мысленно подправь до правдоподобного варианта. Не цепляйся к буквальному тексту — анализируй смысл.

## Когда какой режим

- **Диалог**: короткое сообщение, простой вопрос, продолжение разговора → отвечай напрямую без обращения к БД.
- **Запись дневника**: длинное сообщение, отчёт о событии, рефлексия, специальный вопрос с просьбой обратиться к контексту → запусти ниже описанный workflow.

## Workflow для записи дневника

### Шаг 1. Пойми, о чём сообщение (артефакты: summary и набор тегов)
Прочитай сообщение и мысленно сформируй 5-7 кандидат-тегов из словаря (тема, место, люди, настроение, состояние, о чём). Это твой "ключ" для поиска похожих записей.
Сгенерируй черновое summary 1-2 предложения о чём запись (что произошло, ключевая эмоция, кто фигурирует).

### Шаг 2. Узнай ландшафт тегов
Один раз в начале беседы вызови `GET /stats` — посмотри какие теги существуют и их частоту. Это поможет выбрать правильные ключи для retrieval (если кандидат-тег `nervous` редкий, а `anxious` частый — возьми `anxious`). Результат держи в голове до конца беседы.

### Шаг 3. Достань похожие записи по 2-4 значимым тегам
Для каждого из 2-4 главных тегов вызови `GET /entries/summary?tag=X`. Ответ содержит `id`, `summary` (1-2 предложения о записи) и `tags`. Этого достаточно для оценки релевантности без полного текста.
Если total_pages > 1, начинай просмотр с последней страницы (то есть со свежих последних записей).

Приоритет тегов для retrieval:
1. **Тема** — главный смысловой ключ
2. **Люди** — если в записи фигурирует конкретный человек
3. **Паттерн / состояние** — если запись про повторяющуюся динамику
4. **Место** — обычно как уточняющий

### Шаг 4. Углубись в 3-10 наиболее релевантных записей
По полю `summary` выбери 3-10 записей которые: (а) тематически близки, (б) указывают на повторение паттерна, (в) контрастируют с текущим сообщением. Для каждой вызови `GET /entries/{id}` за полным текстом. Помни: текст — транскрипция, могут быть искажения.

### Шаг 5. Анализ
Опираясь на эти записи + новое сообщение:
- Дай ответ как терапевт: интерпретации, гипотезы, неочевидные связи.


### Шаг 6. Уточни summary и теги
После прочтения похожих записей ты можешь увидеть, что тема не та, что казалась изначально. Уточни:
- **summary** (1-2 предложения о записи)
- **tags** (5-7 шт). Категории: тема, место, люди, настроение, состояние, о чём.

### Шаг 7. Сохрани
Вызови `POST /entries` с полями `voice_text` (исходное сообщение пользователя БЕЗ правок — храним как есть, искажения транскрипции остаются для истории), `summary` (уточнённое — здесь уже подразумевается твой исправленный смысл), `tags` (через запятую).

### Шаг 8. Подтверди
Вызови `GET /entries/{id}` (id из ответа на POST) — убедись что запись, summary и теги сохранились корректно. Если нет — сообщи пользователю.

## Правила тегов
- Каждый тег — одно слово lowercase **латиницей**, без дефисов и пробелов (kebab-case ЗАПРЕЩЁН).
- Имена людей — транслитом (`jenya`), не кириллицей.
- ОБЯЗАТЕЛЬНО хотя бы 1 тег из EVENT, 1-2 из FEELING, 1-2 из PATTERN.
- ПРЕДПОЧИТАЙ теги из словаря — это даёт кластеризацию на Graph view.
- Новый однословный тег вводи только если ничего не подходит. Сначала проверь синонимы: `fear` вместо `nervous`, `shame` вместо `ashamed`, `joy` вместо `joyful`.
## Словарь (7 осей)
- **EVENT** (что произошло): `date, breakup, conflict, reflection, memory, fantasy, plan`
- **FEELING** (эмоция по Plutchik): `joy, sadness, fear, anger, anticipation, shame, remorse, love, optimism, trust`
- **THEME** (область жизни): `dating, family, work, money, body, friendship, identity, growth, creativity`
- **PATTERN** (психодинамика — самое ценное для терапии): `avoidance, idealization, withdrawal, chasing, comparison, fantasizing, perfectionism, abandonment, pleasing, rumination, validation`
- **PERSON**: `father, mother, ex, friend, stranger` + имена транслитом (jenya, …`)
- **PLACE**: `club, gym, yoga, street, home, party, cafe`
- **STATE**: `drunk, sober, tired`

Пример POST:
{
  "voice_text": "Сегодня познакомился с девушкой в клубе...",
  "summary": "Знакомство в клубе",
  "tags": "dating,stranger,club"
}
```

### 4. Actions

Нажми "Add Action":

**Authentication:**
- Type: API Key
- API Key: `<значение DIARY_API_KEY из .env>`
- Auth Type: Custom
- Custom Header Name: `X-API-Key`

**Schema:** вставь содержимое файла `openapi.yaml`

### 5. Сохранить

Publishing: **Only me** (приватный)

## Работа с базой данных

### Подключение к базе

```bash
# На Pi — напрямую
sqlite3 ~/diary-gpt/diary_api/data/diary.db

# Через Docker контейнер
sudo docker exec -it diary-api sqlite3 /app/data/diary.db
```

### Схема таблицы

```sql
CREATE TABLE diary_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,
    voice_text  TEXT    NOT NULL,
    duration    INTEGER DEFAULT 0,
    message_id  INTEGER DEFAULT 0,
    tags        TEXT    DEFAULT '',  -- comma-separated, vocab из 7 осей
    summary     TEXT    DEFAULT ''   -- 1-2 предложения о записи (генерирует GPT)
)
```

### Просмотр записей

```sql
-- Все записи (краткий обзор)
SELECT id, created_at, summary, tags
FROM diary_entries ORDER BY created_at;

-- Полная запись
SELECT voice_text, summary, tags FROM diary_entries WHERE id = 1;

-- Записи по тегу (через LIKE — comma-separated)
SELECT id, created_at, summary FROM diary_entries
WHERE tags LIKE '%rumination%' ORDER BY created_at DESC;

-- Количество записей
SELECT COUNT(*) FROM diary_entries;
```

### Добавление записи вручную

```sql
INSERT INTO diary_entries (user_id, created_at, voice_text, summary, tags, duration, message_id)
VALUES (0, datetime('now'), 'Текст записи', 'Что произошло, 1-2 предложения', 'reflection,sadness,rumination', 0, 0);
```

Или через API (см. секцию "POST /entries" выше).

### Удаление записей

```sql
-- Удалить конкретную запись
DELETE FROM diary_entries WHERE id = 5;

-- Удалить записи за период
DELETE FROM diary_entries WHERE created_at < '2026-01-01';

-- Удалить все записи
DELETE FROM diary_entries;
VACUUM;
```

### Бэкап

```bash
cp ~/diary-gpt/diary_api/data/diary.db ~/diary-gpt/diary_api/data/diary_backup_$(date +%Y%m%d).db
```

### Экспорт

```bash
# CSV
sqlite3 -header -csv ~/diary-gpt/diary_api/data/diary.db \
  "SELECT id, created_at, voice_text, summary, tags FROM diary_entries;" > diary_export.csv

# JSON (через API)
curl -s -H "X-API-Key: YOUR_KEY" -H "ngrok-skip-browser-warning: true" \
  https://YOUR-DOMAIN.ngrok-free.dev/entries > diary_export.json

# Obsidian-vault (markdown) — лежит в GitHub yourname/diary-vault,
# обновляется автоматически контейнером diary-sync
git clone https://github.com/yourname/diary-vault.git
```

## Структура файлов

```
diary_api/
├── .env.example          # Шаблон переменных окружения
├── .gitignore
├── Dockerfile            # Контейнер FastAPI
├── docker-compose.yml    # API + ngrok + diary-sync
├── api.py                # FastAPI сервер
├── openapi.yaml          # OpenAPI схема для ChatGPT Actions
├── requirements.txt
├── scripts/
│   └── export_to_vault.py  # Bulk-экспорт SQLite → .md (локально, разовый)
└── sync/                 # Контейнер diary-sync
    ├── Dockerfile
    ├── requirements.txt
    └── sync_vault.py     # Цикл sync БД → GitHub vault
```

## Troubleshooting

**ngrok ERR_NGROK_107 (invalid authtoken):**
- Проверь authtoken на https://dashboard.ngrok.com/get-started/your-authtoken
- Убедись что в `.env` нет лишних пробелов

**ngrok ERR_NGROK_334 (endpoint already online):**
- Другой ngrok процесс использует тот же домен
- `sudo pkill -9 -f ngrok` и перезапусти

**API возвращает 401:**
- Неверный API ключ в заголовке `X-API-Key`

**ChatGPT не вызывает Actions:**
- Проверь что Actions настроены с правильным URL и API key
- Попробуй написать "загрузи мои записи дневника"

**diary-sync не пушит в GitHub (403):**
- Проверь scope PAT: должно быть Contents: Read+Write на репо `yourname/diary-vault`
- Token хранится в `.env` как `GITHUB_DIARY_TOKEN`
- После замены токена: `sudo docker compose restart diary-sync`

**diary-sync пушит одно и то же / залип в цикле:**
- Удали state файл: `sudo rm /path/to/diary_api/sync_state/vault_sync_state.json && sudo docker restart diary-sync`
- На следующем тике контейнер пересинхронит всё с нуля

**Конфликт между ручными правками в GitHub и autosync:**
- diary-sync использует Contents API с SHA от GitHub — конфликты ловятся автоматически.
- Но если редактировал `.md` файл руками в GitHub UI, изменения перезапишутся при следующем push из БД (DB — источник правды).
- Хочешь отредактировать — правь `summary`/`tags` в БД через `UPDATE diary_entries SET ... WHERE id = X`, sync подхватит.
