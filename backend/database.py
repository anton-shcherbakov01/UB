import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
from datetime import datetime

# URL для Async (FastAPI)
DATABASE_URL_ASYNC = os.getenv("DATABASE_URL", "postgresql+asyncpg://wb_user:wb_secret_password@db:5432/wb_monitor")
# URL для Sync (Celery) - просто меняем драйвер в строке
DATABASE_URL_SYNC = DATABASE_URL_ASYNC.replace("+asyncpg", "")

# 1. Асинхронный движок (для API)
engine_async = create_async_engine(DATABASE_URL_ASYNC, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine_async, class_=AsyncSession, expire_on_commit=False)

# 2. Синхронный движок (для Celery Tasks)
engine_sync = create_engine(DATABASE_URL_SYNC, echo=False)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_sync)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    subscription_plan = Column(String, default="free")
    subscription_end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("MonitoredItem", back_populates="owner", cascade="all, delete-orphan")

class MonitoredItem(Base):
    __tablename__ = "monitored_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(Integer, index=True)
    name = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="items")
    prices = relationship("PriceHistory", back_populates="item", cascade="all, delete-orphan")

class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("monitored_items.id"))
    wallet_price = Column(Integer)
    standard_price = Column(Integer)
    base_price = Column(Integer)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    item = relationship("MonitoredItem", back_populates="prices")

# Инициализация таблиц (асинхронно)
async def init_db():
    async with engine_async.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Зависимость для FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session