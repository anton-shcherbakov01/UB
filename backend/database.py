import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger, Text, Float
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
from datetime import datetime

# Настройки подключения
DATABASE_URL_ASYNC = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:wb_secret_password@db:5432/wb_monitor")
# Для Воркера (Celery) используем синхронный драйвер
DATABASE_URL_SYNC = DATABASE_URL_ASYNC.replace("+asyncpg", "")

# 1. Асинхронный движок (FastAPI)
engine_async = create_async_engine(DATABASE_URL_ASYNC, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine_async, class_=AsyncSession, expire_on_commit=False)

# 2. Синхронный движок (Celery)
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
    
    # Новые поля для API WB и уведомлений
    wb_api_token = Column(String, nullable=True)
    last_order_check = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    items = relationship("MonitoredItem", back_populates="owner", cascade="all, delete-orphan")
    history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    costs = relationship("ProductCost", back_populates="user", cascade="all, delete-orphan")
    seo_keywords = relationship("SeoPosition", back_populates="user", cascade="all, delete-orphan")
    bidder_logs = relationship("BidderLog", back_populates="user", cascade="all, delete-orphan")

class ProductCost(Base):
    """
    Таблица для хранения себестоимости СОБСТВЕННЫХ товаров пользователя.
    Используется для расчета Unit-экономики и P&L во внутренней аналитике.
    """
    __tablename__ = "product_costs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger, index=True)
    cost_price = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="costs")

class MonitoredItem(Base):
    """
    Таблица для ВНЕШНЕГО мониторинга (конкуренты).
    """
    __tablename__ = "monitored_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger, index=True)
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

class SearchHistory(Base):
    __tablename__ = "search_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger)
    request_type = Column(String) 
    title = Column(String)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="history")

class SeoPosition(Base):
    """
    Новая таблица: Трекинг позиций (SERP)
    """
    __tablename__ = "seo_positions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger)
    keyword = Column(String)
    position = Column(Integer, default=0) # 0 - не найдено в топ-100
    last_check = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="seo_keywords")

class BidderLog(Base):
    """
    NEW: Логирование работы RTB биддера.
    Используется для демонстрации эффективности Safe Mode и отладки.
    """
    __tablename__ = "bidder_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    campaign_id = Column(BigInteger, index=True)
    
    current_pos = Column(Integer)
    target_pos = Column(Integer)
    
    previous_bid = Column(Integer)
    calculated_bid = Column(Integer)
    
    # "Сэкономлено" = (Ставка конкурента - Наша ставка) или (Старая ставка - Новая ставка)
    saved_amount = Column(Integer, default=0)
    
    action = Column(String) # 'update', 'safe_mode', 'paused', 'low_ctr'
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="bidder_logs")

async def init_db():
    async with engine_async.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session