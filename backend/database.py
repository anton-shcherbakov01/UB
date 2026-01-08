import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://wb_user:wb_secret_password@localhost:5432/wb_monitor")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# Таблица отслеживаемых товаров
class MonitoredItem(Base):
    __tablename__ = "monitored_items"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(Integer, unique=True, index=True)
    name = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с историей цен
    prices = relationship("PriceHistory", back_populates="item", cascade="all, delete")

# Таблица истории цен (Снимок цены во времени)
class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("monitored_items.id"))
    wallet_price = Column(Integer)
    standard_price = Column(Integer)
    base_price = Column(Integer)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("MonitoredItem", back_populates="prices")

# Функция для создания таблиц при старте
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Получение сессии БД
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session