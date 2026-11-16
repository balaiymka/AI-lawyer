# Портал ЖКХ 24 — AI-юрист по закону и НПА РК

Веб-сервис и AI-ассистент по жилищному законодательству Республики Казахстан: понимает казахский, русский и шала-қазақша, отвечает со ссылками на статьи НПА, строит план действий, генерирует документы, считает пеню и кворум, проверяет договоры.

## Документация

| Документ | Содержание |
|---|---|
| [01-architecture.md](docs/01-architecture.md) | Архитектура, RAG-пайплайн, схема PostgreSQL и Qdrant, API |
| [02-system-prompt.md](docs/02-system-prompt.md) | Промпты нормализатора и AI-юриста, JSON-схемы, примеры шала-қазақша |
| [03-design-system.md](docs/03-design-system.md) | Дизайн-система по референсам (тёмная «билет» + светлая «тёплое стекло») |
| [04-structure-and-roadmap.md](docs/04-structure-and-roadmap.md) | Структура папок и план по спринтам |

## Структура

```
apps/api   FastAPI, модели БД, миграции Alembic, ингест законов с Adilet (ingest/)
apps/web   Next.js 15 + Tailwind 4: главная страница, темы, KZ/RU
infra      docker-compose: Postgres, Qdrant, Redis, MinIO, API
```

## Запуск

```bash
cp .env.example .env
```

Инфраструктура (нужен Docker):

```bash
docker compose -f infra/docker-compose.yml up -d postgres qdrant redis minio
```

Backend (Python 3.12+):

```bash
cd apps/api && python3 -m venv .venv && .venv/bin/pip install -e ".[dev,ingest]" && .venv/bin/playwright install chromium
```

```bash
cd apps/api && .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --reload
```

Загрузка Закона «О жилищных отношениях» (рендер kk+ru с Adilet → разбор → PostgreSQL):

```bash
cd apps/api && .venv/bin/python -m ingest fetch ZHO && .venv/bin/python -m ingest load ZHO
```

Проверка: `GET http://localhost:8000/v1/library/acts/zho/articles/42`

Тесты:

```bash
cd apps/api && .venv/bin/python -m pytest
```

Frontend:

```bash
cd apps/web && npm install && npm run dev
```

Открыть http://localhost:3000 (перенаправит на `/ru` или `/kk`).
# AI-lawyer
