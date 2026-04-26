## Что внутри

```text
pill-vision-baseline/
├── backend/              # Flask API
│   └── app/
│       ├── main.py        # /api/analyze, /api/search-json, /api/health
│       ├── model_client.py# LM Studio/mock адаптер + 3-stage prompts
│       ├── db.py          # запросы в PostgreSQL
│       └── scoring.py     # нормализация и скоринг
├── frontend/             # React + Vite + Nginx
├── db/init.sql           # схема и заполненные drug_profiles
├── docker-compose.yml
└── .env.example
```

## Быстрый запуск

```bash
cp .env.example .env
docker compose up --build
```

Открыть фронт:

```text
http://localhost:8080
```

## Запуск с LM Studio + Qwen


```env
MODEL_MODE=lmstudio
MODEL_BASE_URL=http://host.docker.internal:1234/v1
MODEL_NAME=qwen2.5-vl-7b-instruct
MODEL_TIMEOUT_SEC=180
MODEL_TEMPERATURE=0.0
```


## Как работает 3-stage pipeline

Backend делает три последовательных запроса:

1. **Stage 1** — классифицирует dosage form по фото:

```json
{"dosage_form": "soft capsule"}
```

2. **Stage 2** — повторно отправляет фото и извлекает признаки, но dosage form уже фиксируется ответом Stage 1.

3. **Stage 3** — отправляет только JSON из Stage 2 без картинки и просит модель провалидировать/нормализовать значения.