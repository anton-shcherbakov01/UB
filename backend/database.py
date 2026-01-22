import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger, Text, Float, DECIMAL
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, configure_mappers
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
import logging
from datetime import datetime

logger = logging.getLogger("DATABASE")

# Настройки подключения
DATABASE_URL_ASYNC = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:wb_secret_password@db:5432/wb_monitor")

if "+asyncpg" in DATABASE_URL_ASYNC:
    DATABASE_URL_SYNC = DATABASE_URL_ASYNC.replace("+asyncpg", "")
else:
    DATABASE_URL_SYNC = DATABASE_URL_ASYNC

# 1. Асинхронный движок (FastAPI/Bot)
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
    subscription_plan = Column(String, default="start")
    
    # Поля API WB
    wb_api_token = Column(String, nullable=True)
    last_order_check = Column(DateTime, nullable=True)
    
    # SaaS поля
    subscription_expires_at = Column(DateTime, nullable=True)
    is_recurring = Column(Boolean, default=False)
    
    # Quota and Usage Tracking
    usage_reset_date = Column(DateTime, nullable=True)
    ai_requests_used = Column(Integer, default=0)
    extra_ai_balance = Column(Integer, default=0)
    cluster_requests_used = Column(Integer, default=0)
    
    # Offer acceptance
    offer_accepted = Column(Boolean, default=False)
    offer_accepted_at = Column(DateTime, nullable=True)
    privacy_accepted = Column(Boolean, default=False)
    privacy_accepted_at = Column(DateTime, nullable=True)
    
    # --- PARTNER SYSTEM UPDATE ---
    referrer_id = Column(BigInteger, nullable=True, index=True)  # ID партнера (Telegram ID)
    # -----------------------------

    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    items = relationship("MonitoredItem", back_populates="owner", cascade="all, delete-orphan")
    history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    costs = relationship("ProductCost", back_populates="user", cascade="all, delete-orphan")
    seo_keywords = relationship("SeoPosition", back_populates="user", cascade="all, delete-orphan")
    bidder_logs = relationship("BidderLog", back_populates="user", cascade="all, delete-orphan")
    bidder_settings = relationship("BidderSettings", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    supply_settings = relationship("SupplySettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    slot_monitors = relationship("SlotMonitor", back_populates="user", cascade="all, delete-orphan")
    notification_settings = relationship("NotificationSettings", uselist=False, back_populates="user", cascade="all, delete-orphan")

# --- НОВЫЕ ТАБЛИЦЫ ДЛЯ ПАРТНЕРКИ ---

class Partner(Base):
    """Таблица партнеров (агентов)"""
    __tablename__ = "partners"
    
    user_id = Column(BigInteger, primary_key=True) # Telegram ID
    username = Column(String, nullable=True)
    balance = Column(DECIMAL(10, 2), default=0)
    total_earned = Column(DECIMAL(10, 2), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Lead(Base):
    """Таблица лидов (бронь юзернеймов)"""
    __tablename__ = "leads"
    
    username = Column(String, primary_key=True) # @username (lowercase, no @)
    reserved_by_partner_id = Column(BigInteger, index=True)
    reserved_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime) # reserved_at + 24 hours
    status = Column(String, default='reserved') # 'reserved', 'converted', 'lost'

class PayoutRequest(Base):
    """Заявки на вывод средств"""
    __tablename__ = "payout_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(BigInteger, index=True)
    amount = Column(DECIMAL(10, 2))
    details = Column(String) # Номер карты / телефон
    status = Column(String, default='pending') # 'pending', 'paid', 'rejected'
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

# -----------------------------------

class NotificationSettings(Base):
    __tablename__ = "notification_settings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    notify_new_orders = Column(Boolean, default=True)
    notify_buyouts = Column(Boolean, default=True)
    notify_hourly_stats = Column(Boolean, default=False)
    summary_interval = Column(Integer, default=1)
    last_summary_at = Column(DateTime, nullable=True)
    show_daily_revenue = Column(Boolean, default=True)
    show_funnel = Column(Boolean, default=True)
    user = relationship("User", back_populates="notification_settings")

class SlotMonitor(Base):
    __tablename__ = "slot_monitors"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    warehouse_id = Column(Integer)
    warehouse_name = Column(String)
    target_coefficient = Column(Integer, default=0)
    box_type = Column(String, default="all")
    is_active = Column(Boolean, default=True)
    last_notified_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="slot_monitors")

class SupplySettings(Base):
    __tablename__ = "supply_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_time = Column(Integer, default=7)
    min_stock_days = Column(Integer, default=14)
    planning_period = Column(Integer, default=30)
    abc_a_share = Column(Float, default=80.0)
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
    logistics = Column(Float, nullable=True)
    commission_percent = Column(Float, nullable=True)
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
    __tablename__ = "bidder_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    campaign_id = Column(BigInteger, unique=True, index=True)
    is_active = Column(Boolean, default=False)
    target_pos = Column(Integer, default=1)
    max_bid = Column(Integer, default=500)
    min_bid = Column(Integer, default=125)
    keyword = Column(String, nullable=True)
    check_organic = Column(Boolean, default=False)
    last_check_time = Column(DateTime, default=datetime.utcnow)
    target_cpa = Column(Integer, default=0)
    max_cpm = Column(Integer, default=2000)
    strategy = Column(String, default="pid")
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
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="bidder_logs")

try:
    configure_mappers()
except Exception as e:
    logger.error(f"Mapper configuration failed: {e}")

async def init_db():
    async with engine_async.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session