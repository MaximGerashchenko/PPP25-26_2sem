import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


DATABASE_URL = "sqlite:///./etl_service.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


class ItemCategory(Base):
    __tablename__ = "item_categories"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), primary_key=True)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    items: Mapped[list["Item"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    items: Mapped[list["Item"]] = relationship(
        secondary="item_categories",
        back_populates="categories",
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    source: Mapped[Source] = relationship(back_populates="items")
    categories: Mapped[list[Category]] = relationship(
        secondary="item_categories",
        back_populates="items",
    )
    events: Mapped[list["ItemEvent"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemEvent.created_at",
    )


class ItemEvent(Base):
    __tablename__ = "item_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    item: Mapped[Item] = relationship(back_populates="events")


class ServiceTask(Base):
    __tablename__ = "service_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(String(255), default="Task queued", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class SourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    base_url: str = Field(min_length=5, max_length=255)


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    created_at: datetime


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ItemBase(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    price: float = Field(gt=0)
    source_id: int
    category_ids: list[int] = Field(default_factory=list)


class ItemCreate(ItemBase):
    pass


class ItemPut(ItemBase):
    is_active: bool = True


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: float | None = Field(default=None, gt=0)
    source_id: int | None = None
    is_active: bool | None = None
    category_ids: list[int] | None = None


class ItemEventCreate(BaseModel):
    event_type: str = Field(min_length=2, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class ItemEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    event_type: str
    payload: str
    created_at: datetime


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    price: float
    is_active: bool
    source_id: int
    created_at: datetime
    updated_at: datetime
    source: SourceRead
    categories: list[CategoryRead]


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_type: str
    status: str
    progress: int
    message: str
    result_json: str
    created_at: datetime
    updated_at: datetime


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(client_id, []).append(websocket)

    def disconnect(self, client_id: str, websocket: WebSocket) -> None:
        clients = self.connections.get(client_id, [])
        if websocket in clients:
            clients.remove(websocket)
        if not clients and client_id in self.connections:
            del self.connections[client_id]

    async def broadcast(self, client_id: str, payload: dict[str, Any]) -> None:
        for websocket in list(self.connections.get(client_id, [])):
            await websocket.send_json(payload)


manager = ConnectionManager()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_item_event(db: Session, item: Item, event_type: str, payload: dict[str, Any]) -> ItemEvent:
    event = ItemEvent(
        item_id=item.id,
        event_type=event_type,
        payload=json.dumps(payload, ensure_ascii=True),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def require_source(db: Session, source_id: int) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    return source


def load_categories(db: Session, category_ids: list[int]) -> list[Category]:
    if not category_ids:
        return []
    categories = db.query(Category).filter(Category.id.in_(category_ids)).all()
    if len(categories) != len(set(category_ids)):
        raise HTTPException(status_code=404, detail="One or more categories were not found")
    return categories


def require_item(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item


def seed_data() -> None:
    with SessionLocal() as db:
        if db.query(Source).count() > 0:
            return

        source_1 = Source(name="Books ETL", base_url="https://books.example/api")
        source_2 = Source(name="Electronics ETL", base_url="https://electronics.example/api")
        db.add_all([source_1, source_2])
        db.flush()

        categories = [
            Category(name="books"),
            Category(name="education"),
            Category(name="electronics"),
            Category(name="gadgets"),
        ]
        db.add_all(categories)
        db.flush()

        item_1 = Item(
            title="FastAPI in Practice",
            description="Unified record imported from ETL sources.",
            price=29.99,
            source_id=source_1.id,
            categories=[categories[0], categories[1]],
        )
        item_2 = Item(
            title="Wireless Keyboard",
            description="Latest normalized offer from supplier feed.",
            price=79.5,
            source_id=source_2.id,
            categories=[categories[2], categories[3]],
        )
        db.add_all([item_1, item_2])
        db.commit()

        db.refresh(item_1)
        db.refresh(item_2)
        create_item_event(db, item_1, "imported", {"source": "initial_seed"})
        create_item_event(db, item_2, "imported", {"source": "initial_seed"})


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_data()


Base.metadata.create_all(bind=engine)
seed_data()

app = FastAPI(
    title="ETL Data Service",
    description="Single-file FastAPI service over ETL-like relational data.",
    version="1.0.0",
)


@app.get("/")
def root(db: Session = Depends(get_db)):
    return {
        "message": "ETL data service is running",
        "sources": db.query(Source).count(),
        "items": db.query(Item).count(),
        "events": db.query(ItemEvent).count(),
    }


@app.get("/sources", response_model=list[SourceRead])
def list_sources(db: Session = Depends(get_db)):
    return db.query(Source).order_by(Source.id).all()


@app.get("/sources/{source_id}", response_model=SourceRead)
def get_source(source_id: int, db: Session = Depends(get_db)):
    return require_source(db, source_id)


@app.post("/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)):
    if db.query(Source).filter(Source.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Source name must be unique")
    source = Source(name=payload.name, base_url=payload.base_url)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@app.get("/categories", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.name).all()


@app.get("/items", response_model=list[ItemRead])
def list_items(
    source_id: int | None = None,
    category_id: int | None = None,
    is_active: bool | None = None,
    q: str | None = Query(default=None, min_length=1),
    min_price: float | None = Query(default=None, gt=0),
    max_price: float | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    query = db.query(Item).distinct().order_by(Item.id)

    if source_id is not None:
        query = query.filter(Item.source_id == source_id)
    if category_id is not None:
        query = query.join(Item.categories).filter(Category.id == category_id)
    if is_active is not None:
        query = query.filter(Item.is_active == is_active)
    if q:
        pattern = f"%{q}%"
        query = query.filter((Item.title.ilike(pattern)) | (Item.description.ilike(pattern)))
    if min_price is not None:
        query = query.filter(Item.price >= min_price)
    if max_price is not None:
        query = query.filter(Item.price <= max_price)

    return query.all()


@app.get("/items/{item_id}", response_model=ItemRead)
def get_item(item_id: int, db: Session = Depends(get_db)):
    return require_item(db, item_id)


@app.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    require_source(db, payload.source_id)
    categories = load_categories(db, payload.category_ids)
    item = Item(
        title=payload.title,
        description=payload.description,
        price=payload.price,
        source_id=payload.source_id,
        categories=categories,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    create_item_event(db, item, "created", {"title": item.title, "price": item.price})
    db.refresh(item)
    return item


@app.put("/items/{item_id}", response_model=ItemRead)
def replace_item(item_id: int, payload: ItemPut, db: Session = Depends(get_db)):
    item = require_item(db, item_id)
    require_source(db, payload.source_id)
    item.title = payload.title
    item.description = payload.description
    item.price = payload.price
    item.source_id = payload.source_id
    item.is_active = payload.is_active
    item.categories = load_categories(db, payload.category_ids)
    db.commit()
    db.refresh(item)
    create_item_event(db, item, "replaced", {"title": item.title, "price": item.price})
    db.refresh(item)
    return item


@app.patch("/items/{item_id}", response_model=ItemRead)
def update_item(item_id: int, payload: ItemPatch, db: Session = Depends(get_db)):
    item = require_item(db, item_id)
    data = payload.model_dump(exclude_unset=True)

    if "source_id" in data:
        require_source(db, data["source_id"])
    if "category_ids" in data:
        item.categories = load_categories(db, data.pop("category_ids"))

    for field, value in data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    create_item_event(db, item, "patched", data)
    db.refresh(item)
    return item


@app.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = require_item(db, item_id)
    item.is_active = False
    db.commit()
    create_item_event(db, item, "deactivated", {"item_id": item.id})
    return {"message": f"Item {item_id} deactivated"}


@app.get("/items/{item_id}/events", response_model=list[ItemEventRead])
def list_item_events(item_id: int, db: Session = Depends(get_db)):
    require_item(db, item_id)
    return db.query(ItemEvent).filter(ItemEvent.item_id == item_id).order_by(ItemEvent.id).all()


@app.post("/items/{item_id}/events", response_model=ItemEventRead, status_code=status.HTTP_201_CREATED)
def add_item_event(item_id: int, payload: ItemEventCreate, db: Session = Depends(get_db)):
    item = require_item(db, item_id)
    return create_item_event(db, item, payload.event_type, payload.payload)


@app.get("/stats/summary")
def stats_summary(db: Session = Depends(get_db)):
    per_source = (
        db.query(Source.name, func.count(Item.id).label("items_count"))
        .join(Item, Item.source_id == Source.id)
        .group_by(Source.name)
        .order_by(Source.name)
        .all()
    )
    return {
        "total_sources": db.query(Source).count(),
        "total_items": db.query(Item).count(),
        "active_items": db.query(Item).filter(Item.is_active.is_(True)).count(),
        "avg_price": round(db.query(func.avg(Item.price)).scalar() or 0, 2),
        "items_per_source": [{"source": name, "items_count": count} for name, count in per_source],
    }


async def run_rebuild_stats(task_id: str, client_id: str | None = None) -> None:
    updates = [
        ("running", 10, "Preparing source data"),
        ("running", 45, "Calculating item counters"),
        ("running", 80, "Calculating price aggregates"),
        ("completed", 100, "Statistics rebuilt successfully"),
    ]

    with SessionLocal() as db:
        task = db.get(ServiceTask, task_id)
        if not task:
            return

        for status_value, progress_value, message in updates:
            task.status = status_value
            task.progress = progress_value
            task.message = message
            if status_value == "completed":
                result = {
                    "total_items": db.query(Item).count(),
                    "active_items": db.query(Item).filter(Item.is_active.is_(True)).count(),
                    "average_price": round(db.query(func.avg(Item.price)).scalar() or 0, 2),
                }
                task.result_json = json.dumps(result, ensure_ascii=True)
            db.commit()
            db.refresh(task)
            if client_id:
                await manager.broadcast(
                    client_id,
                    {
                        "task_id": task.id,
                        "status": task.status,
                        "progress": task.progress,
                        "message": task.message,
                    },
                )
            await asyncio.sleep(0.05)


@app.post("/tasks/rebuild-stats", response_model=TaskRead, status_code=status.HTTP_202_ACCEPTED)
async def rebuild_stats(client_id: str | None = None, db: Session = Depends(get_db)):
    task = ServiceTask(
        task_type="rebuild_stats",
        status="pending",
        progress=0,
        message="Task queued",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    asyncio.create_task(run_rebuild_stats(task.id, client_id))
    return task


@app.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(ServiceTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.websocket("/ws/{client_id}")
async def websocket_updates(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    try:
        await websocket.send_json({"message": "connected", "client_id": client_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id, websocket)


client = TestClient(app)


def test_get_items() -> None:
    reset_database()
    response = client.get("/items")
    assert response.status_code == 200
    assert len(response.json()) >= 2


def test_post_item() -> None:
    reset_database()
    response = client.post(
        "/items",
        json={
            "title": "USB Hub",
            "description": "Created from test payload",
            "price": 39.99,
            "source_id": 2,
            "category_ids": [3, 4],
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "USB Hub"


def test_put_item() -> None:
    reset_database()
    response = client.put(
        "/items/1",
        json={
            "title": "FastAPI in Practice 2nd Edition",
            "description": "Replaced item payload",
            "price": 35.5,
            "source_id": 1,
            "is_active": True,
            "category_ids": [1],
        },
    )
    assert response.status_code == 200
    assert response.json()["price"] == 35.5


def test_patch_item() -> None:
    reset_database()
    response = client.patch("/items/1", json={"price": 31.25, "is_active": False})
    assert response.status_code == 200
    body = response.json()
    assert body["price"] == 31.25
    assert body["is_active"] is False


def test_delete_item() -> None:
    reset_database()
    response = client.delete("/items/1")
    assert response.status_code == 200
    after = client.get("/items/1")
    assert after.status_code == 200
    assert after.json()["is_active"] is False


def test_rebuild_stats_task() -> None:
    reset_database()
    response = client.post("/tasks/rebuild-stats")
    assert response.status_code == 202
    task_id = response.json()["id"]
    assert len(task_id) == 36

    for _ in range(20):
        status_response = client.get(f"/tasks/{task_id}")
        assert status_response.status_code == 200
        body = status_response.json()
        if body["status"] == "completed":
            assert body["progress"] == 100
            return
        time.sleep(0.05)

    raise AssertionError("Task did not complete in time")


def test_not_found_and_validation() -> None:
    reset_database()
    not_found = client.get("/items/999")
    invalid = client.post(
        "/items",
        json={
            "title": "X",
            "description": "Too short title",
            "price": -10,
            "source_id": 1,
            "category_ids": [],
        },
    )
    assert not_found.status_code == 404
    assert invalid.status_code == 422


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
