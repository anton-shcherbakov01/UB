#================
#File: backend/database.py
#================
import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger, Text, Float, Enum
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
from datetime import datetime

# Connection Settings
DATABASE_URL_ASYNC = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:wb_secret_password@db:5432/wb_monitor")
# Sync driver for Celery/Workers
DATABASE_URL_SYNC = DATABASE_URL_ASYNC.replace("+asyncpg", "")

# 1. Async Engine (FastAPI)
engine_async = create_async_engine(DATABASE_URL_ASYNC, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine_async, class_=AsyncSession, expire_on_commit=False)

# 2. Sync Engine (Celery)
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
    
    # API & Notification fields
    wb_api_token = Column(String, nullable=True)
    last_order_check = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    items = relationship("MonitoredItem", back_populates="owner", cascade="all, delete-orphan")
    history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    costs = relationship("ProductCost", back_populates="user", cascade="all, delete-orphan")
    seo_keywords = relationship("SeoPosition", back_populates="user", cascade="all, delete-orphan")
    campaigns = relationship("BidderCampaign", back_populates="user", cascade="all, delete-orphan")

class ProductCost(Base):
    """
    COGS storage for Unit Economy calculations.
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
    External competitor monitoring.
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
    SERP Tracking.
    """
    __tablename__ = "seo_positions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sku = Column(BigInteger)
    keyword = Column(String)
    position = Column(Integer, default=0) # 0 - not in top 100
    last_check = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="seo_keywords")

# --- RTB BIDDER MODELS ---

class BidderCampaign(Base):
    """
    Configuration for Auto-Bidder campaigns.
    """
    __tablename__ = "bidder_campaigns"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    wb_campaign_id = Column(Integer, unique=True, index=True) # Real WB Campaign ID
    name = Column(String)
    
    # Strategy Settings
    target_position = Column(Integer, default=1) # Desired place (1, 2, 3...)
    max_bid = Column(Integer, default=500)       # Ceiling
    min_bid = Column(Integer, default=125)       # Floor
    target_cpa = Column(Integer, nullable=True)  # Max cost per action
    
    # PID Coefficients (Advanced Tuning)
    kp = Column(Float, default=1.0) # Proportional
    ki = Column(Float, default=0.1) # Integral
    kd = Column(Float, default=0.5) # Derivative
    
    # Control Flags
    is_active = Column(Boolean, default=False)
    safe_mode = Column(Boolean, default=True) # If True, logs only, no real API calls
    
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="campaigns")
    logs = relationship("BidderLog", back_populates="campaign", cascade="all, delete-orphan")

class BidderLog(Base):
    """
    History of bid changes for auditing and 'Safe Mode' demos.
    """
    __tablename__ = "bidder_logs"
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("bidder_campaigns.id"))
    
    timestamp = Column(DateTime, default=datetime.utcnow)
    current_pos = Column(Integer)
    competitor_bid = Column(Integer) # Bid of the neighbor
    calculated_bid = Column(Integer)
    action_taken = Column(String) # 'UPDATED', 'SKIPPED_SAFE_MODE', 'PAUSED_CPA'
    budget_saved = Column(Integer, default=0) # Virtual metric for safe mode
    
    campaign = relationship("BidderCampaign", back_populates="logs")

async def init_db():
    async with engine_async.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session