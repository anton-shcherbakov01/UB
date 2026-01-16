import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis
from dotenv import load_dotenv

from celery_app import REDIS_URL
from routers import users, finance, monitoring, seo, ai, payments, admin, supply, dashboard, analytics, slots, notifications
# В РАЗРАБОТКЕ: from routers import bidder

load_dotenv()
logger = logging.getLogger("API")

app = FastAPI(title="JuicyStat")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(users.router)
app.include_router(finance.router)
app.include_router(monitoring.router)
app.include_router(seo.router)
app.include_router(ai.router)
app.include_router(payments.router)
app.include_router(admin.router)
# В РАЗРАБОТКЕ: app.include_router(bidder.router)
app.include_router(supply.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(slots.router)
app.include_router(notifications.router)

@app.on_event("startup")
async def on_startup(): 
    try:
        r = aioredis.from_url(REDIS_URL, encoding="utf8", decode_responses=True)
        FastAPICache.init(RedisBackend(r), prefix="fastapi-cache")
        logger.info("✅ Redis cache initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Redis cache: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)