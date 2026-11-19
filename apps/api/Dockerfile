FROM python:3.12-slim

# Код лежит в /srv/apps/api, как в репозитории: config.py ищет корень проекта (data/, .env) на 4 уровня выше.
WORKDIR /srv/apps/api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/srv/hf

# Сначала зависимости — слой кешируется, пока не меняется pyproject.toml.
# torch только CPU-сборка: на сервере нет видеокарты, CUDA-колёса весили бы ~3 ГБ лишних.
COPY pyproject.toml ./
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && mkdir -p app ingest && touch app/__init__.py ingest/__init__.py \
 && pip install --no-cache-dir ".[ml]" && pip uninstall -y zhkh24-api

COPY . .
RUN pip install --no-cache-dir --no-deps -e .

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
