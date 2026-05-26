# ETL FastAPI Service

Однофайловый веб‑сервис над ETL‑данными на `FastAPI + SQLAlchemy + SQLite`.

## Что реализовано

- 5 связанных таблиц: `sources`, `items`, `categories`, `item_categories`, `item_events`
- дополнительная служебная таблица `service_tasks`
- CRUD и выборки по ETL‑данным
- фоновая долгая задача `rebuild-stats`
- WebSocket для уведомлений о статусе задач
- тесты `pytest` без запуска `uvicorn`

## HTTP‑ручки

- `GET /`
- `GET /sources`
- `GET /sources/{source_id}`
- `POST /sources`
- `GET /categories`
- `GET /items`
- `GET /items/{item_id}`
- `POST /items`
- `PUT /items/{item_id}`
- `PATCH /items/{item_id}`
- `DELETE /items/{item_id}`
- `GET /items/{item_id}/events`
- `POST /items/{item_id}/events`
- `GET /stats/summary`
- `POST /tasks/rebuild-stats`
- `GET /tasks/{task_id}`
- `WS /ws/{client_id}`

## Как запустить

1. Создать и активировать виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Установить зависимости:

```powershell
pip install fastapi uvicorn sqlalchemy pydantic pytest httpx
```

3. Запустить сервер:

```powershell
python main.py
```

После запуска будут доступны:

- Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## Как работают данные

При первом запуске автоматически создаётся файл БД `etl_service.db` и заполняется начальными ETL‑подобными данными:

- источники (`sources`)
- товары (`items`)
- категории (`categories`)
- события по товарам (`item_events`)

Удаление товара сделано как мягкое удаление: запись не удаляется физически, а переводится в `is_active = false`.

## Примеры команд

Получить список товаров:

```powershell
curl http://127.0.0.1:8000/items
```

Создать товар:

```powershell
curl -X POST http://127.0.0.1:8000/items ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Monitor 27\",\"description\":\"New ETL item\",\"price\":199.99,\"source_id\":2,\"category_ids\":[3,4]}"
```

Запустить долгую задачу:

```powershell
curl -X POST http://127.0.0.1:8000/tasks/rebuild-stats
```

Проверить статус задачи:

```powershell
curl http://127.0.0.1:8000/tasks/<task_id>
```

## Как запустить тесты

```powershell
pytest main.py -v
```

Тесты покрывают:

- `GET`
- `POST`
- `PUT`
- `PATCH`
- `DELETE`
- happy‑path для долгой задачи
- ошибки `404` и `422`

## Важно

В задании про дополнительные возможности упомянуты `Celery + Redis`. В этой версии сделана упрощённая асинхронная фоновая задача средствами FastAPI/`asyncio`, чтобы уложиться в требование “только 2 файла” и сохранить простой запуск через терминал. Если нужно, следующей итерацией можно заменить этот блок на полноценную связку `Celery + Redis`.
