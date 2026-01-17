import os
import io
import logging
import asyncio
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel
from fpdf import FPDF

from database import get_db, User, SeoPosition, SearchHistory
from dependencies import get_current_user
from dependencies.quota import QuotaCheck, increment_usage
from tasks import generate_seo_task, check_seo_position_task, cluster_keywords_task
from services.selenium_search import selenium_service, GEO_COOKIES
from services.queue_service import queue_service
from parser_service import parser_service
from config.plans import has_feature
import json

executor = ThreadPoolExecutor(max_workers=3)

logger = logging.getLogger("SEO-Router")
router = APIRouter(prefix="/api", tags=["SEO"])

class SeoTrackRequest(BaseModel):
    sku: int
    keyword: str

class SeoGenRequest(BaseModel):
    sku: int
    keywords: List[str]
    tone: str
    title_len: Optional[int] = 100
    desc_len: Optional[int] = 1000

class ClusterRequest(BaseModel):
    sku: int
    keywords: List[str]

class SeoPdfRequest(BaseModel):
    sku: str
    title: str
    description: str
    features: Optional[Dict[str, str]] = {}
    faq: Optional[List[Dict[str, str]]] = []

@router.get("/seo/regions")
async def get_regions():
    return [{"key": k, "label": k.upper()} for k in GEO_COOKIES.keys()]

@router.get("/seo/position")
async def check_position(
    query: str, 
    sku: int, 
    geo: str = Query("moscow")
):
    logger.info(f"🔎 SELENIUM SEARCH: SKU={sku} Query='{query}' Geo={geo}")

    if geo not in GEO_COOKIES:
        geo = "moscow"

    loop = asyncio.get_event_loop()
    try:
        # 3. Запускаем синхронную функцию Selenium в отдельном потоке executor'а
        result = await loop.run_in_executor(
            executor, 
            selenium_service.get_position, 
            query, 
            sku, 
            geo
        )
        
        if not result['found']:
            return {
                "status": "not_found", 
                "message": f"Не найдено (проверено {result.get('page', 0)} стр)",
                "data": result
            }
        
        logger.info(f"✅ FOUND! Pos: {result['position']}")
        return {"status": "success", "data": result}
        
    except Exception as e:
        logger.error(f"Selenium Critical Error: {e}")
        # Если драйвер упал, пробуем его перезапустить для следующих запросов
        try:
            selenium_service.close()
        except: pass
        raise HTTPException(500, detail=f"Ошибка парсера: {str(e)}")

@router.post("/seo/track")
async def track_position(req: SeoTrackRequest, user: User = Depends(get_current_user)):
    task = check_seo_position_task.delay(req.sku, req.keyword, user.id)
    return {"status": "accepted", "task_id": task.id}

@router.get("/seo/positions")
async def get_seo_positions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SeoPosition).where(SeoPosition.user_id == user.id).order_by(SeoPosition.last_check.desc()))
    return res.scalars().all()

@router.delete("/seo/positions/{id}")
async def delete_seo_position(id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SeoPosition).where(SeoPosition.id == id, SeoPosition.user_id == user.id))
    await db.commit()
    return {"status": "deleted"}

@router.get("/seo/parse/{sku}")
async def parse_seo_keywords(sku: int, user: User = Depends(get_current_user)):
    res = await parser_service.get_seo_data(sku) 
    if res.get("status") == "error":
        raise HTTPException(400, res.get("message"))
    return res

@router.post("/seo/generate")
async def generate_seo_content(
    req: SeoGenRequest,
    user: User = Depends(QuotaCheck("ai_requests")),
    db: AsyncSession = Depends(get_db)
):
    """Генерация GEO-контента. Списывает ai_requests. Выбор тона — только Аналитик+."""
    if not has_feature(user.subscription_plan, "seo_semantics") and req.tone != "Продающий":
        raise HTTPException(403, "Выбор тона голоса доступен на тарифе Аналитик и выше")
    try:
        task = generate_seo_task.delay(req.keywords, req.tone, req.sku, user.id, req.title_len, req.desc_len)
        if not task or not task.id:
            raise HTTPException(500, "Не удалось создать задачу генерации")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SEO generate task creation failed: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Ошибка запуска: {str(e)}")

    queue_info = {"queue": "normal", "position": 0, "is_priority": False}
    try:
        queue_info = queue_service.add_task_to_queue(
            task_id=task.id, user_id=user.id, user_plan=user.subscription_plan, task_type="seo_generate"
        )
    except Exception as qe:
        logger.warning(f"Queue service error (non-critical): {qe}")

    try:
        await increment_usage(user, "ai_requests", amount=1, db=db)
    except Exception as ue:
        logger.error(f"Failed to increment usage for user {user.id}: {ue}", exc_info=True)

    return {
        "status": "accepted",
        "task_id": task.id,
        "queue": queue_info.get("queue", "normal"),
        "position": queue_info.get("position", 0),
        "is_priority": queue_info.get("is_priority", False),
    }


@router.post("/seo/cluster")
async def cluster_keywords_endpoint(
    req: ClusterRequest,
    user: User = Depends(QuotaCheck("ai_requests", "seo_semantics")),
    db: AsyncSession = Depends(get_db),
):
    """Кластеризация ключевых слов (BERT). Доступна на тарифе Аналитик+. Списывает ai_requests."""
    try:
        task = cluster_keywords_task.delay(req.keywords, user.id, req.sku)
        if not task or not task.id:
            raise HTTPException(500, "Не удалось создать задачу кластеризации")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cluster task creation failed: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Ошибка запуска: {str(e)}")

    queue_info = {"queue": "normal", "position": 0, "is_priority": False}
    try:
        queue_info = queue_service.add_task_to_queue(
            task_id=task.id, user_id=user.id, user_plan=user.subscription_plan, task_type="cluster_keywords"
        )
    except Exception as qe:
        logger.warning(f"Queue service error (non-critical): {qe}")

    try:
        await increment_usage(user, "ai_requests", amount=1, db=db)
    except Exception as ue:
        logger.error(f"Failed to increment usage for user {user.id}: {ue}", exc_info=True)

    return {
        "status": "accepted",
        "task_id": task.id,
        "queue": queue_info.get("queue", "normal"),
        "position": queue_info.get("position", 0),
        "is_priority": queue_info.get("is_priority", False),
    }

def _build_seo_pdf_bytes(sku: str, title: str, description: str, features: dict, faq: list) -> bytes:
    """Общая логика сборки PDF для SEO-отчёта (POST и GET)."""
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "./DejaVuSans.ttf"]
    font_path = next((p for p in font_paths if os.path.exists(p)), None)
    pdf = FPDF()
    pdf.add_page()
    font_family = "Arial"
    if font_path:
        try:
            pdf.add_font("DejaVu", "", font_path, uni=True)
            pdf.add_font("DejaVu", "B", font_path, uni=True)
            font_family = "DejaVu"
        except Exception as e:
            logger.error(f"Font loading error: {e}")

    pdf.set_font(font_family, "B", 16)
    pdf.cell(0, 10, f"GEO SEO Report: SKU {sku}", ln=1, align="C")
    pdf.ln(5)

    pdf.set_font(font_family, "B", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "OPTIMIZED TITLE", ln=1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_family, "", 11)
    pdf.multi_cell(0, 6, title or "")
    pdf.ln(5)

    pdf.set_font(font_family, "B", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "DESCRIPTION", ln=1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_family, "", 10)
    pdf.multi_cell(0, 5, description or "")
    pdf.ln(10)

    if features:
        pdf.set_font(font_family, "B", 12)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, "SPECIFICATIONS (Features)", ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font_family, "", 9)
        for k, v in (features or {}).items():
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(60, 8, str(k), border=1, fill=True)
            pdf.cell(0, 8, str(v), border=1)
            pdf.ln()
        pdf.ln(10)

    if faq:
        pdf.set_font(font_family, "B", 12)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, "FAQ (User Intent)", ln=1)
        pdf.set_text_color(0, 0, 0)
        for item in faq:
            pdf.set_font(font_family, "B", 10)
            pdf.multi_cell(0, 5, f"Q: {item.get('question', '')}")
            pdf.set_x(pdf.l_margin)
            pdf.set_font(font_family, "", 10)
            pdf.multi_cell(0, 5, f"A: {item.get('answer', '')}")
            pdf.ln(3)

    pdf.set_y(-30)
    pdf.set_font(font_family, "", 8)
    pdf.set_text_color(128)
    pdf.cell(0, 10, f"Generated by WB Analytics AI • {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

    pdf_content = pdf.output(dest="S")
    return pdf_content.encode("latin-1") if isinstance(pdf_content, str) else pdf_content


@router.get("/report/seo-pdf/{sku}")
async def download_seo_pdf_by_sku(
    sku: int,
    user: User = Depends(QuotaCheck(feature_flag="pnl_full")),
    db: AsyncSession = Depends(get_db),
):
    """Скачать PDF по последнему SEO-отчёту для SKU (из истории). Для мобильных — window.open(URL)."""
    stmt = (
        select(SearchHistory)
        .where(
            SearchHistory.user_id == user.id,
            SearchHistory.sku == sku,
            SearchHistory.request_type == "seo",
        )
        .order_by(SearchHistory.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalars().first()
    if not row or not row.result_json:
        raise HTTPException(404, "SEO-отчёт не найден. Сначала создайте GEO-контент.")

    try:
        data = json.loads(row.result_json)
    except Exception:
        raise HTTPException(500, "Ошибка данных отчёта")

    gen = data.get("generated_content") or {}
    if not isinstance(gen, dict):
        raise HTTPException(500, "Некорректная структура")

    pdf_bytes = _build_seo_pdf_bytes(
        sku=str(sku),
        title=gen.get("title", ""),
        description=gen.get("description", ""),
        features=gen.get("structured_features") or {},
        faq=gen.get("faq") or [],
    )
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="seo_report_{sku}.pdf"'},
    )


@router.post("/report/seo-pdf/generate")
async def generate_seo_pdf_report(
    req: SeoPdfRequest,
    user: User = Depends(QuotaCheck(feature_flag="pnl_full")),
):
    """Генерация PDF из переданного контента (для обратной совместимости). Скачивание — Аналитик+."""
    pdf_bytes = _build_seo_pdf_bytes(
        sku=req.sku,
        title=req.title,
        description=req.description,
        features=req.features or {},
        faq=req.faq or [],
    )
    from urllib.parse import quote
    filename = f"seo_report_{req.sku}.pdf"
    filename_encoded = quote(filename.encode("utf-8"))
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename_encoded}',
        "Content-Length": str(len(pdf_bytes)),
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)