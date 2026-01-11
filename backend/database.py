import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger, Text, Float
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
from datetime import datetime

# Настройки подключения
DATABASE_URL_ASYNC = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:wb_secret_password@db:5432/wb_monitor")
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
    
    wb_api_token = Column(String, nullable=True)
    last_order_check = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    items = relationship("MonitoredItem", back_populates="owner", cascade="all, delete-orphan")
    history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    costs = relationship("ProductCost", back_populates="user", cascade="all, delete-orphan")
    seo_keywords = relationship("SeoPosition", back_populates="user", cascade="all, delete-orphan")
    bidder_configs = relationship("BidderConfig", back_populates="user", cascade="all, delete-orphan")

class BidderConfig(Base):
    """
    Конфигурация автобиддера для конкретной кампании.
    Хранит настройки PID-регулятора и текущее состояние.
    """
    __tablename__ = "bidder_configs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    campaign_id = Column(BigInteger, index=True) # ID кампании на WB
    campaign_name = Column(String, nullable=True)
    
    # Настройки стратегии
    target_position = Column(Integer, default=5) # Целевое место
    max_bid = Column(Integer, default=500)       # Максимальная ставка
    min_bid = Column(Integer, default=125)       # Минимальная ставка
    keyword = Column(String, nullable=True)      # Ключевое слово для проверки позиций
    
    # PID коэффициенты (настраиваемые)
    kp = Column(Float, default=1.0)
    ki = Column(Float, default=0.1)
    kd = Column(Float, default=0.05)
    
    # Состояние PID (для интегральной составляющей)
    accumulated_error = Column(Float, default=0.0)
    last_error = Column(Float, default=0.0)
    
    is_active = Column(Boolean, default=False)   # Включен ли биддер
    safe_mode = Column(Boolean, default=True)    # Safe Mode: только логирование, без реальной ставки
    
    last_check = Column(DateTime, default=datetime.utcnow)
    last_log = Column(Text, nullable=True)       # Последнее действие (текстом)

    user = relationship("User", back_populates="bidder_configs")

class ProductCost(Base):
    __tablename__ = "product_costs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger, index=True)
    cost_price = Column(Float, default=0.0)
    fulfillment_cost = Column(Float, default=0.0)
    external_marketing = Column(Float, default=0.0)
    tax_rate = Column(Float, default=6.0)
    updated_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="costs")

class MonitoredItem(Base):
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
    __tablename__ = "seo_positions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger)
    keyword = Column(String)
    position = Column(Integer, default=0)
    last_check = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="seo_keywords")

async def init_db():
    async with engine_async.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session