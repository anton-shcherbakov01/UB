import os
import io
import logging
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from fpdf import FPDF

from database import get_db, User, SeoPosition
from dependencies import get_current_user
from tasks import generate_seo_task, check_seo_position_task, cluster_keywords_task
from services.wb_search import wb_search_service, GEO_ZONES
from parser_service import parser_service

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

@router.get("/regions")
@cache(expire=86400) # Кэшируем список регионов на сутки, он меняется редко
async def get_regions():
    """
    Отдает список доступных регионов для фронтенда.
    """
    return [{"key": k, "label": k.upper()} for k in GEO_ZONES.keys()]

@router.get("/position")
@cache(expire=300) # Кэшируем результат поиска на 5 минут
async def check_position(
    query: str, 
    sku: int, 
    geo: str = Query("moscow", description="Region key: moscow, spb, kazan...")
):
    """
    Мгновенная проверка позиции через Mobile API
    Возвращает:
    - Точную позицию
    - Факт авторекламы (CPM)
    - Соседей (кто выше/ниже) для анализа конкуренции
    """
    if not query or not sku:
        raise HTTPException(status_code=400, detail="Query and SKU are required")

    # Нормализация региона
    if geo not in GEO_ZONES:
        geo = "moscow"

    try:
        # Вызываем сервис
        result = await wb_search_service.get_sku_position(query, sku, geo=geo)
    except Exception as e:
        # Логируем и отдаем 500, но аккуратно
        raise HTTPException(status_code=500, detail=f"Search service error: {str(e)}")
    
    # Формируем красивый ответ
    response_data = {
        "status": "success" if result['found'] else "not_found",
        "geo": geo,
        "query": query,
        "sku": sku,
        "data": result
    }
    
    return response_data

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
async def generate_seo_content(req: SeoGenRequest, user: User = Depends(get_current_user)):
    task = generate_seo_task.delay(req.keywords, req.tone, req.sku, user.id, req.title_len, req.desc_len)
    return {"status": "accepted", "task_id": task.id}

@router.post("/seo/cluster")
async def cluster_keywords_endpoint(req: ClusterRequest, user: User = Depends(get_current_user)):
    task = cluster_keywords_task.delay(req.keywords, user.id, req.sku)
    return {"status": "accepted", "task_id": task.id}

@router.post("/report/seo-pdf/generate")
async def generate_seo_pdf_report(req: SeoPdfRequest, user: User = Depends(get_current_user)):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "./DejaVuSans.ttf" 
    ]
    font_path = None
    for path in font_paths:
        if os.path.exists(path):
            font_path = path
            break
            
    pdf = FPDF()
    pdf.add_page()
    
    font_family = 'Arial' 
    if font_path:
        try:
            pdf.add_font('DejaVu', '', font_path, uni=True)
            pdf.add_font('DejaVu', 'B', font_path, uni=True) 
            font_family = 'DejaVu'
        except Exception as e:
            logger.error(f"Font loading error: {e}")
    
    pdf.set_font(font_family, 'B', 16)
    pdf.cell(0, 10, f"GEO SEO Report: SKU {req.sku}", ln=1, align='C')
    pdf.ln(5)
    
    pdf.set_font(font_family, 'B', 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "OPTIMIZED TITLE", ln=1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_family, '', 11)
    pdf.multi_cell(0, 6, req.title)
    pdf.ln(5)
    
    pdf.set_font(font_family, 'B', 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "DESCRIPTION", ln=1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_family, '', 10)
    pdf.multi_cell(0, 5, req.description)
    pdf.ln(10)
    
    if req.features:
        pdf.set_font(font_family, 'B', 12)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, "SPECIFICATIONS (Features)", ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font_family, '', 9)
        for k, v in req.features.items():
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(60, 8, str(k), border=1, fill=True)
            pdf.cell(0, 8, str(v), border=1)
            pdf.ln()
        pdf.ln(10)

    if req.faq:
        pdf.set_font(font_family, 'B', 12)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, "FAQ (User Intent)", ln=1)
        pdf.set_text_color(0, 0, 0)
        for item in req.faq:
            pdf.set_font(font_family, 'B', 10)
            pdf.multi_cell(0, 5, f"Q: {item.get('question', '')}")
            pdf.set_x(pdf.l_margin)
            pdf.set_font(font_family, '', 10)
            pdf.multi_cell(0, 5, f"A: {item.get('answer', '')}")
            pdf.ln(3)

    pdf.set_y(-30)
    pdf.set_font(font_family, '', 8)
    pdf.set_text_color(128)
    pdf.cell(0, 10, f"Generated by WB Analytics AI • {datetime.now().strftime('%Y-%m-%d %H:%M')}", align='C')

    pdf_content = pdf.output(dest='S')
    if isinstance(pdf_content, str): 
        pdf_bytes = pdf_content.encode('latin-1') 
    else: 
        pdf_bytes = pdf_content

    return StreamingResponse(
        io.BytesIO(pdf_bytes), 
        media_type='application/pdf', 
        headers={'Content-Disposition': f'attachment; filename="seo_report_{req.sku}.pdf"'}
    )