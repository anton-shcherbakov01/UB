import os
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, BigInteger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://wb_user:wb_secret_password@db:5432/wb_monitor")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True) # ID пользователя в Telegram
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    
    # Подписка
    subscription_plan = Column(String, default="free") # free, pro, enterprise
    subscription_end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("MonitoredItem", back_populates="owner", cascade="all, delete")

class MonitoredItem(Base):
    __tablename__ = "monitored_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) # Привязка к владельцу
    sku = Column(Integer, index=True)
    name = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="items")
    prices = relationship("PriceHistory", back_populates="item", cascade="all, delete")

class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("monitored_items.id"))
    wallet_price = Column(Integer)
    standard_price = Column(Integer)
    base_price = Column(Integer)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("MonitoredItem", back_populates="prices")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session