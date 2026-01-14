import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger, Text, Float
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
from datetime import datetime


# Настройки подключения
DATABASE_URL_ASYNC = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:wb_secret_password@db:5432/wb_monitor")

# Для синхронного драйвера (Celery/Migrate)
if "+asyncpg" in DATABASE_URL_ASYNC:
    DATABASE_URL_SYNC = DATABASE_URL_ASYNC.replace("+asyncpg", "")
else:
    DATABASE_URL_SYNC = DATABASE_URL_ASYNC

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
    
    # Поля API WB
    wb_api_token = Column(String, nullable=True)
    last_order_check = Column(DateTime, nullable=True)
    
    # SaaS поля
    subscription_expires_at = Column(DateTime, nullable=True)
    is_recurring = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    items = relationship("MonitoredItem", back_populates="owner", cascade="all, delete-orphan")
    history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    costs = relationship("ProductCost", back_populates="user", cascade="all, delete-orphan")
    seo_keywords = relationship("SeoPosition", back_populates="user", cascade="all, delete-orphan")
    bidder_logs = relationship("BidderLog", back_populates="user", cascade="all, delete-orphan")
    bidder_settings = relationship("BidderSettings", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

class SupplySettings(Base):
    """
    Персональные настройки логистики для расчета поставок.
    """
    __tablename__ = "supply_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    lead_time = Column(Integer, default=7)          # Срок доставки до склада WB (дней)
    min_stock_days = Column(Integer, default=14)    # Минимальный запас (дней продаж)
    planning_period = Column(Integer, default=30)   # Горизонт планирования (дней)
    
    # Коэффициенты ABC анализа (можно настроить границы групп)
    abc_a_share = Column(Float, default=80.0)       # Граница группы А (%)
    
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="supply_settings")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    provider_payment_id = Column(String, index=True)
    amount = Column(Integer)
    currency = Column(String, default="RUB")
    status = Column(String)
    plan_id = Column(String)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="payments")

class ProductCost(Base):
    __tablename__ = "product_costs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger, index=True)
    
    cost_price = Column(Integer, default=0)
    
    # --- ПОЛЯ ДЛЯ UNIT-ЭКОНОМИКИ ---
    logistics = Column(Float, nullable=True)
    commission_percent = Column(Float, nullable=True)
    # -------------------------------
    
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

class BidderSettings(Base):
    """
    Настройки автобиддера для конкретной кампании.
    """
    __tablename__ = "bidder_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    campaign_id = Column(BigInteger, unique=True, index=True)
    
    is_active = Column(Boolean, default=False)
    target_pos = Column(Integer, default=1)   # Целевая позиция
    max_bid = Column(Integer, default=500)    # Максимальная ставка (RUB)
    min_bid = Column(Integer, default=125)    # Минимальная ставка
    
    # Safety Layers
    target_cpa = Column(Integer, default=0)   # Целевая цена действия (0 = выкл)
    max_cpm = Column(Integer, default=2000)   # Хард лимит CPM
    strategy = Column(String, default="pid")  # 'pid', 'shadowing', 'fixed'
    
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="bidder_settings")

class BidderLog(Base):
    __tablename__ = "bidder_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    campaign_id = Column(BigInteger, index=True)
    
    current_pos = Column(Integer)
    target_pos = Column(Integer)
    
    previous_bid = Column(Integer)
    calculated_bid = Column(Integer)
    
    saved_amount = Column(Integer, default=0)
    
    action = Column(String) # 'update', 'safe_mode', 'paused', 'low_ctr', 'cpa_guard'
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="bidder_logs")

async def init_db():
    async with engine_async.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session