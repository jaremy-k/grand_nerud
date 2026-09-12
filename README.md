# grand_nerud

CRM API для сделок с нерудными материалами (продажа, утилизация, доставка).

## Стек

- FastAPI + MongoDB (Motor)
- Poetry
- Docker Compose
- JWT (Bearer token)

## Быстрый старт

```bash
cp env.example .env
# заполните переменные окружения

poetry install
poetry run uvicorn app.main:app --reload --port 5003
```

Документация API: `http://localhost:5003/docs`

## Документация

- [Правила расчёта сделок (для клиента)](docs/calculation-rules.md) — API, формат `schema`, DSL, примеры запросов

## Docker

```bash
cp env.example .env_prod
# заполните .env_prod

docker compose up --build
```

API: `http://localhost:5007`

## Авторизация

```bash
# Регистрация (если ALLOW_REGISTRATION=true)
curl -X POST http://localhost:5003/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}'

# Логин
curl -X POST http://localhost:5003/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}'

# Запросы с токеном
curl http://localhost:5003/materials \
  -H "Authorization: Bearer <access_token>"
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `SECRET_KEY` | Секрет для JWT |
| `MONGO_*` | Подключение к MongoDB |
| `API_KONTRAGENTPRO_*` | API KontragentPro для поиска компаний по ИНН |
| `S3_*` | Опционально, для файлового хранилища |
| `CORS_ORIGINS` | `*` или список через запятую |
| `ALLOW_REGISTRATION` | Публичная регистрация (`true`/`false`) |

## Структура

```
app/
├── core/           # общие утилиты, pagination, entity services
├── repositories/   # MongoRepository — доступ к данным
├── integrations/   # KontragentPro, S3
├── deals/          # сделки (ядро)
├── companies/      # контрагенты
├── materials/      # материалы
└── ...
```

## Тесты

```bash
poetry run pytest
```

## Healthcheck

`GET /health` — проверка доступности MongoDB.
