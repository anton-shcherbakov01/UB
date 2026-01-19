import logging
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
import redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from database import get_db, User, MonitoredItem, SearchHistory
from dependencies import get_current_user, get_redis_client
from config.plans import TIERS
from celery_app import REDIS_URL, celery_app

logger = logging.getLogger("Admin")
router = APIRouter(prefix="/api/admin", tags=["Admin"])

class PlanChangeRequest(BaseModel):
    plan_id: str

@router.get("/stats")
async def get_admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Базовая статистика (для обратной совместимости)"""
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    users = (await db.execute(select(func.count(User.id)))).scalar()
    items = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    return {"total_users": users, "total_items_monitored": items, "server_status": "Online (v2.0)"}

@router.get("/users/stats")
async def get_users_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Детальная статистика пользователей"""
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Общее количество пользователей
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    
    # Платные пользователи (subscription_plan != 'start' ИЛИ subscription_expires_at > now)
    paid_users = (await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.subscription_plan != 'start',
                User.subscription_expires_at > now
            )
        )
    )).scalar() or 0
    
    # Пользователи по тарифам
    plan_stats = {}
    for plan_key in ['start', 'analyst', 'strategist']:
        count = (await db.execute(
            select(func.count(User.id)).where(User.subscription_plan == plan_key)
        )).scalar() or 0
        plan_stats[plan_key] = count
    
    # Активные пользователи (использовали любой сервис за период)
    active_7d = (await db.execute(
        select(func.count(func.distinct(SearchHistory.user_id))).where(
            SearchHistory.created_at >= week_ago
        )
    )).scalar() or 0
    
    active_30d = (await db.execute(
        select(func.count(func.distinct(SearchHistory.user_id))).where(
            SearchHistory.created_at >= month_ago
        )
    )).scalar() or 0
    
    # Новые пользователи
    new_today = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )).scalar() or 0
    
    new_week = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= week_ago)
    )).scalar() or 0
    
    new_month = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= month_ago)
    )).scalar() or 0
    
    # Распределение по датам регистрации (последние 30 дней для графика)
    registration_data = []
    for i in range(30):
        day_start = (now - timedelta(days=29-i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = (await db.execute(
            select(func.count(User.id)).where(
                and_(User.created_at >= day_start, User.created_at < day_end)
            )
        )).scalar() or 0
        registration_data.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "count": count
        })
    
    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "paid_percentage": round((paid_users / total_users * 100) if total_users > 0 else 0, 2),
        "plan_distribution": plan_stats,
        "active_users": {
            "last_7_days": active_7d,
            "last_30_days": active_30d
        },
        "new_users": {
            "today": new_today,
            "week": new_week,
            "month": new_month
        },
        "registration_chart": registration_data
    }

@router.post("/set-plan")
async def set_user_plan(
    request: PlanChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Изменение тарифа текущего пользователя (для админов для тестирования).
    """
    if not user.is_admin:
        raise HTTPException(403, "Forbidden")
    
    # Проверяем, что план существует
    if request.plan_id not in TIERS:
        raise HTTPException(400, detail=f"Неверный план. Доступные: {', '.join(TIERS.keys())}")
    
    # Обновляем план пользователя
    user.subscription_plan = request.plan_id
    
    # Если план не бесплатный, устанавливаем срок действия подписки на 30 дней
    plan_config = TIERS[request.plan_id]
    now = datetime.utcnow()
    if plan_config.get("price", 0) > 0:
        user.subscription_expires_at = now + timedelta(days=30)
    else:
        user.subscription_expires_at = None
    
    # Сбрасываем использование квот
    user.ai_requests_used = 0
    user.extra_ai_balance = 0
    user.usage_reset_date = now + timedelta(days=30)
    
    # Сохраняем изменения - используем merge для безопасности
    # Это гарантирует, что объект будет правильно обновлен в сессии
    merged_user = await db.merge(user)
    
    # Flush перед commit для гарантии записи изменений
    await db.flush()
    
    # Commit транзакции
    await db.commit()
    
    # Обновляем объект из БД, чтобы получить актуальные значения
    await db.refresh(merged_user, attribute_names=["subscription_plan", "subscription_expires_at", "ai_requests_used", "extra_ai_balance", "usage_reset_date"])
    
    # Обновляем оригинальный объект значениями из merged объекта
    user.subscription_plan = merged_user.subscription_plan
    user.subscription_expires_at = merged_user.subscription_expires_at
    user.ai_requests_used = merged_user.ai_requests_used
    user.extra_ai_balance = merged_user.extra_ai_balance
    user.usage_reset_date = merged_user.usage_reset_date
    
    # Логируем успешное изменение для отладки
    logger.info(f"User {user.id} (telegram_id={user.telegram_id}) plan changed to {request.plan_id}")
    
    return {
        "status": "success",
        "message": f"Тариф изменен на {plan_config.get('name', request.plan_id)}",
        "plan": user.subscription_plan,
        "plan_name": plan_config.get("name", request.plan_id),
        "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
    }

@router.get("/services/stats")
async def get_services_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Статистика использования сервисов"""
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    
    # Список всех сервисов
    service_names = {
        'ai': 'AI анализ отзывов',
        'seo': 'SEO генератор',
        'seo_tracker': 'SEO трекер',
        'pnl': 'P&L отчеты',
        'unit_economy': 'Unit экономика',
        'supply': 'Анализ поставок',
        'forensics': 'Форензика',
        'cashgap': 'Cash Gap',
        'price': 'Мониторинг цен',
        'slots': 'Слоты'
    }
    
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    # Общая статистика по каждому сервису
    services_data = []
    total_usage = 0
    
    for service_key, service_name in service_names.items():
        # Количество использований
        total_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(SearchHistory.request_type == service_key)
        )).scalar() or 0
        
        week_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(
                and_(
                    SearchHistory.request_type == service_key,
                    SearchHistory.created_at >= week_ago
                )
            )
        )).scalar() or 0
        
        month_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(
                and_(
                    SearchHistory.request_type == service_key,
                    SearchHistory.created_at >= month_ago
                )
            )
        )).scalar() or 0
        
        # Уникальные пользователи
        unique_users = (await db.execute(
            select(func.count(func.distinct(SearchHistory.user_id))).where(
                SearchHistory.request_type == service_key
            )
        )).scalar() or 0
        
        # Последнее использование
        last_used = (await db.execute(
            select(func.max(SearchHistory.created_at)).where(
                SearchHistory.request_type == service_key
            )
        )).scalar()
        
        services_data.append({
            "service_key": service_key,
            "service_name": service_name,
            "total_usage": total_count,
            "week_usage": week_count,
            "month_usage": month_count,
            "unique_users": unique_users,
            "last_used": last_used.isoformat() if last_used else None
        })
        
        total_usage += total_count
    
    # Рейтинг популярности (топ-10)
    services_data_sorted = sorted(services_data, key=lambda x: x['total_usage'], reverse=True)[:10]
    for service in services_data_sorted:
        service['percentage'] = round((service['total_usage'] / total_usage * 100) if total_usage > 0 else 0, 2)
    
    # Динамика использования по дням (последние 30 дней)
    usage_chart = []
    for i in range(30):
        day_start = (now - timedelta(days=29-i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        day_data = {"date": day_start.strftime("%Y-%m-%d")}
        for service_key in service_names.keys():
            count = (await db.execute(
                select(func.count(SearchHistory.id)).where(
                    and_(
                        SearchHistory.request_type == service_key,
                        SearchHistory.created_at >= day_start,
                        SearchHistory.created_at < day_end
                    )
                )
            )).scalar() or 0
            day_data[service_key] = count
        usage_chart.append(day_data)
    
    return {
        "services": services_data,
        "popularity_ranking": services_data_sorted,
        "usage_chart": usage_chart,
        "total_usage": total_usage
    }

@router.get("/services/detailed")
async def get_services_detailed(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Детальная таблица сервисов с параметрами для сортировки"""
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    
    service_names = {
        'ai': 'AI анализ отзывов',
        'seo': 'SEO генератор',
        'seo_tracker': 'SEO трекер',
        'pnl': 'P&L отчеты',
        'unit_economy': 'Unit экономика',
        'supply': 'Анализ поставок',
        'forensics': 'Форензика',
        'cashgap': 'Cash Gap',
        'price': 'Мониторинг цен',
        'slots': 'Слоты'
    }
    
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    detailed_services = []
    
    for service_key, service_name in service_names.items():
        # Количество использований
        total_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(SearchHistory.request_type == service_key)
        )).scalar() or 0
        
        today_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(
                and_(
                    SearchHistory.request_type == service_key,
                    SearchHistory.created_at >= today_start
                )
            )
        )).scalar() or 0
        
        week_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(
                and_(
                    SearchHistory.request_type == service_key,
                    SearchHistory.created_at >= week_ago
                )
            )
        )).scalar() or 0
        
        month_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(
                and_(
                    SearchHistory.request_type == service_key,
                    SearchHistory.created_at >= month_ago
                )
            )
        )).scalar() or 0
        
        # Уникальные пользователи
        unique_users = (await db.execute(
            select(func.count(func.distinct(SearchHistory.user_id))).where(
                SearchHistory.request_type == service_key
            )
        )).scalar() or 0
        
        # Последнее использование
        last_used = (await db.execute(
            select(func.max(SearchHistory.created_at)).where(
                SearchHistory.request_type == service_key
            )
        )).scalar()
        
        # Пиковое использование (максимум за день за последние 30 дней)
        peak_usage = 0
        for i in range(30):
            day_start = (now - timedelta(days=29-i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            day_count = (await db.execute(
                select(func.count(SearchHistory.id)).where(
                    and_(
                        SearchHistory.request_type == service_key,
                        SearchHistory.created_at >= day_start,
                        SearchHistory.created_at < day_end
                    )
                )
            )).scalar() or 0
            peak_usage = max(peak_usage, day_count)
        
        # Тренд (сравнение последней недели с предыдущей)
        prev_week_start = week_ago - timedelta(days=7)
        prev_week_count = (await db.execute(
            select(func.count(SearchHistory.id)).where(
                and_(
                    SearchHistory.request_type == service_key,
                    SearchHistory.created_at >= prev_week_start,
                    SearchHistory.created_at < week_ago
                )
            )
        )).scalar() or 0
        
        trend = "stable"
        if prev_week_count > 0:
            change_percent = ((week_count - prev_week_count) / prev_week_count) * 100
            if change_percent > 10:
                trend = "up"
            elif change_percent < -10:
                trend = "down"
        
        detailed_services.append({
            "service_key": service_key,
            "service_name": service_name,
            "usage": {
                "total": total_count,
                "today": today_count,
                "week": week_count,
                "month": month_count
            },
            "unique_users": unique_users,
            "last_used": last_used.isoformat() if last_used else None,
            "peak_usage": peak_usage,
            "trend": trend
        })
    
    return {"services": detailed_services}

@router.get("/server/metrics")
async def get_server_metrics(user: User = Depends(get_current_user)):
    """Метрики нагрузки сервера"""
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    
    metrics = {}
    
    # Метрики Celery
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        scheduled_tasks = inspect.scheduled()
        reserved_tasks = inspect.reserved()
        
        total_active = sum(len(tasks) for tasks in (active_tasks or {}).values())
        total_scheduled = sum(len(tasks) for tasks in (scheduled_tasks or {}).values())
        total_reserved = sum(len(tasks) for tasks in (reserved_tasks or {}).values())
        
        # Статистика по очередям из Redis
        r_client = get_redis_client()
        priority_queue_size = r_client.llen('celery:priority') if r_client else 0
        normal_queue_size = r_client.llen('celery:normal') if r_client else 0
        
        metrics["celery"] = {
            "active_tasks": total_active,
            "scheduled_tasks": total_scheduled,
            "reserved_tasks": total_reserved,
            "queue_sizes": {
                "priority": priority_queue_size,
                "normal": normal_queue_size
            }
        }
    except Exception as e:
        logger.error(f"Error getting Celery metrics: {e}")
        metrics["celery"] = {"error": str(e)}
    
    # Метрики Redis
    try:
        r_client = get_redis_client()
        if r_client:
            info = r_client.info()
            metrics["redis"] = {
                "used_memory_mb": round(info.get('used_memory', 0) / 1024 / 1024, 2),
                "used_memory_human": info.get('used_memory_human', '0B'),
                "total_keys": r_client.dbsize(),
                "connected_clients": info.get('connected_clients', 0)
            }
        else:
            metrics["redis"] = {"error": "Redis not available"}
    except Exception as e:
        logger.error(f"Error getting Redis metrics: {e}")
        metrics["redis"] = {"error": str(e)}
    
    # Системные метрики (требует psutil)
    if PSUTIL_AVAILABLE:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            metrics["system"] = {
                "cpu_percent": cpu_percent,
                "memory": {
                    "total_mb": round(memory.total / 1024 / 1024, 2),
                    "used_mb": round(memory.used / 1024 / 1024, 2),
                    "available_mb": round(memory.available / 1024 / 1024, 2),
                    "percent": memory.percent
                },
                "disk": {
                    "total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
                    "used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
                    "free_gb": round(disk.free / 1024 / 1024 / 1024, 2),
                    "percent": round((disk.used / disk.total) * 100, 2)
                },
                "load_average": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            metrics["system"] = {"error": str(e)}
    else:
        metrics["system"] = {"error": "psutil not installed"}
    
    # Метрики API (базовая информация, детальная статистика требует middleware)
    metrics["api"] = {
        "note": "Detailed API metrics require middleware implementation",
        "status": "operational"
    }
    
    return metrics

@router.get("/analytics/overview")
async def get_analytics_overview(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Общая аналитика для админа"""
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    
    now = datetime.utcnow()
    month_ago = now - timedelta(days=30)
    
    # График регистраций (уже есть в users/stats, но дублируем для удобства)
    registration_chart = []
    for i in range(30):
        day_start = (now - timedelta(days=29-i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = (await db.execute(
            select(func.count(User.id)).where(
                and_(User.created_at >= day_start, User.created_at < day_end)
            )
        )).scalar() or 0
        registration_chart.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "count": count
        })
    
    # График использования сервисов (последние 30 дней)
    service_names = {
        'ai': 'AI анализ отзывов',
        'seo': 'SEO генератор',
        'seo_tracker': 'SEO трекер',
        'pnl': 'P&L отчеты',
        'unit_economy': 'Unit экономика',
        'supply': 'Анализ поставок',
        'forensics': 'Форензика',
        'cashgap': 'Cash Gap',
        'price': 'Мониторинг цен',
        'slots': 'Слоты'
    }
    
    services_usage_chart = []
    for i in range(30):
        day_start = (now - timedelta(days=29-i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        day_data = {"date": day_start.strftime("%Y-%m-%d")}
        for service_key in service_names.keys():
            count = (await db.execute(
                select(func.count(SearchHistory.id)).where(
                    and_(
                        SearchHistory.request_type == service_key,
                        SearchHistory.created_at >= day_start,
                        SearchHistory.created_at < day_end
                    )
                )
            )).scalar() or 0
            day_data[service_key] = count
        services_usage_chart.append(day_data)
    
    # Распределение пользователей по тарифам (для pie chart)
    plan_distribution = []
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    for plan_key in ['start', 'analyst', 'strategist']:
        count = (await db.execute(
            select(func.count(User.id)).where(User.subscription_plan == plan_key)
        )).scalar() or 0
        if total_users > 0:
            plan_distribution.append({
                "plan": plan_key,
                "count": count,
                "percentage": round((count / total_users) * 100, 2)
            })
    
    # Топ-10 самых активных пользователей
    top_users = (await db.execute(
        select(
            User.id,
            User.username,
            User.first_name,
            User.subscription_plan,
            func.count(SearchHistory.id).label('usage_count')
        )
        .join(SearchHistory, User.id == SearchHistory.user_id)
        .where(SearchHistory.created_at >= month_ago)
        .group_by(User.id, User.username, User.first_name, User.subscription_plan)
        .order_by(func.count(SearchHistory.id).desc())
        .limit(10)
    )).all()
    
    top_users_list = []
    for u in top_users:
        top_users_list.append({
            "user_id": u.id,
            "username": u.username or "Unknown",
            "first_name": u.first_name or "Unknown",
            "plan": u.subscription_plan,
            "usage_count": u.usage_count
        })
    
    # Конверсия из бесплатных в платных
    free_users = (await db.execute(
        select(func.count(User.id)).where(User.subscription_plan == 'start')
    )).scalar() or 0
    
    paid_users = (await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.subscription_plan != 'start',
                User.subscription_expires_at > now
            )
        )
    )).scalar() or 0
    
    conversion_rate = round((paid_users / (free_users + paid_users) * 100) if (free_users + paid_users) > 0 else 0, 2)
    
    return {
        "registration_chart": registration_chart,
        "services_usage_chart": services_usage_chart,
        "plan_distribution": plan_distribution,
        "top_active_users": top_users_list,
        "conversion_rate": conversion_rate,
        "free_users": free_users,
        "paid_users": paid_users
    }