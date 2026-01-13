import os
import io
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fpdf import FPDF
from pydantic import BaseModel

from database import get_db, User, SearchHistory
from dependencies import get_current_user
from tasks import analyze_reviews_task, get_status
from parser_service import parser_service

logger = logging.getLogger("AI-Router")
router = APIRouter(prefix="/api", tags=["AI"])

class AnalyzeRequest(BaseModel):
    sku: int
    limit: int = 100

@router.get("/ai/check/{sku}")
async def check_product_info(sku: int, user: User = Depends(get_current_user)):
    """
    Получает метаданные товара (имя, фото, кол-во отзывов)
    для настройки параметров анализа (слайдер).
    """
    res = await parser_service.get_product_meta(sku)
    if res.get("status") == "error":
        raise HTTPException(400, res.get("message", "Товар не найден"))
    return res

@router.post("/ai/analyze")
async def start_ai_analysis(req: AnalyzeRequest, user: User = Depends(get_current_user)):
    """
    Запуск анализа отзывов с динамическим лимитом.
    """
    # Валидация лимитов (опционально, можно убрать для "безлимита")
    max_limit = 5000 # Техническое ограничение, чтобы не убить сервер
    if req.limit > max_limit:
         req.limit = max_limit
    
    # Для Free тарифа можно оставить жесткий лимит, если нужно
    # if user.subscription_plan == "free" and req.limit > 30:
    #     req.limit = 30

    task = analyze_reviews_task.delay(req.sku, req.limit, user.id)
    return {"status": "accepted", "task_id": task.id}

# Сохраняем старый endpoint для совместимости (если фронт вдруг дернет)
@router.post("/ai/analyze/{sku}")
async def start_ai_analysis_legacy(sku: int, user: User = Depends(get_current_user)):
    limit = 30 if user.subscription_plan == "free" else 100
    task = analyze_reviews_task.delay(sku, limit, user.id)
    return {"status": "accepted", "task_id": task.id}

@router.get("/ai/result/{task_id}")
def get_ai_result(task_id: str):
    """
    Получение результата AI анализа.
    """
    return get_status(task_id)

@router.get("/report/ai-pdf/{sku}")
async def generate_ai_pdf(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free":
        raise HTTPException(403, "Upgrade to PRO")

    stmt = select(SearchHistory).where(
        SearchHistory.user_id == user.id, 
        SearchHistory.sku == sku, 
        SearchHistory.request_type == 'ai'
    ).order_by(SearchHistory.created_at.desc()).limit(1)
    
    history_item = (await db.execute(stmt)).scalars().first()
    
    if not history_item or not history_item.result_json:
        raise HTTPException(404, "Анализ не найден. Сначала запустите AI анализ.")

    try:
        data = json.loads(history_item.result_json)
    except:
        raise HTTPException(500, "Ошибка данных анализа")

    ai_data = data.get('ai_analysis', {})
    if not ai_data:
        raise HTTPException(500, "Некорректная структура данных")

    pdf = FPDF()
    pdf.add_page()

    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font_bold_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    font_family = 'Arial' 
    
    try:
        if os.path.exists(font_path):
            pdf.add_font('DejaVu', '', font_path, uni=True)
            if os.path.exists(font_bold_path):
                pdf.add_font('DejaVu', 'B', font_bold_path, uni=True)
            font_family = 'DejaVu'
        else:
             local_font = "fonts/DejaVuSans.ttf"
             if os.path.exists(local_font):
                 pdf.add_font('DejaVu', '', local_font, uni=True)
                 font_family = 'DejaVu'
    except Exception as e:
        logger.error(f"Font error: {e}")

    pdf.set_font(font_family, '', 14)
    pdf.set_font_size(20)
    pdf.cell(0, 10, txt=f"AI Report: {sku}", ln=1, align='C')
    pdf.set_font_size(12)
    
    product_name = data.get('product_name', 'Product')[:50]
    pdf.cell(0, 10, txt=f"Product: {product_name}...", ln=1, align='C')
    pdf.ln(5)

    if ai_data.get('global_summary'):
        pdf.set_font(font_family, '', 12)
        pdf.cell(0, 10, txt="Резюме:", ln=1)
        pdf.set_font(font_family, '', 10)
        epw = pdf.w - 2 * pdf.l_margin
        pdf.multi_cell(epw, 8, txt=str(ai_data['global_summary']))
        pdf.ln(5)

    if ai_data.get('audience_stats'):
        stats = ai_data['audience_stats']
        pdf.set_font(font_family, '', 12)
        pdf.cell(0, 10, txt="Аудитория:", ln=1)
        pdf.set_font(font_family, '', 10)
        pdf.cell(0, 8, txt=f"- Рационалы: {stats.get('rational_percent')}%", ln=1)
        pdf.cell(0, 8, txt=f"- Эмоционалы: {stats.get('emotional_percent')}%", ln=1)
        pdf.cell(0, 8, txt=f"- Скептики: {stats.get('skeptic_percent')}%", ln=1)
        pdf.ln(5)
        
        if ai_data.get('infographic_recommendation'):
             epw = pdf.w - 2 * pdf.l_margin
             pdf.multi_cell(epw, 8, txt=f"Совет для инфографики: {ai_data['infographic_recommendation']}")
             pdf.ln(5)

    if ai_data.get('aspects'):
        pdf.set_font(font_family, '', 12)
        pdf.cell(0, 10, txt="Ключевые аспекты:", ln=1)
        pdf.set_font(font_family, '', 10)
        epw = pdf.w - 2 * pdf.l_margin
        for asp in ai_data['aspects'][:10]: 
            score = asp.get('sentiment_score', 0)
            pdf.cell(0, 8, txt=f"{asp.get('aspect')} ({score}/9.0)", ln=1)
            pdf.set_font_size(8)
            snippet = str(asp.get('snippet', ''))
            pdf.multi_cell(epw, 5, txt=f"Цитата: {snippet}")
            pdf.ln(2)
            pdf.set_font_size(10)
    
    if ai_data.get('strategy'):
        pdf.ln(5)
        pdf.set_font(font_family, '', 12)
        pdf.cell(0, 10, txt="Стратегия роста:", ln=1)
        pdf.set_font(font_family, '', 10)
        epw = pdf.w - 2 * pdf.l_margin
        for s in ai_data['strategy']:
            text_line = f"- {str(s)}"
            pdf.set_x(pdf.l_margin)
            try:
                pdf.multi_cell(epw, 8, txt=text_line)
            except Exception as e:
                logger.error(f"PDF Render error: {e}")
                pdf.cell(0, 8, txt="- (Ошибка отображения текста)", ln=1)

    pdf_content = pdf.output(dest='S')
    if isinstance(pdf_content, str):
        pdf_bytes = pdf_content.encode('latin-1') 
    else:
        pdf_bytes = pdf_content

    return StreamingResponse(
        io.BytesIO(pdf_bytes), 
        media_type='application/pdf', 
        headers={'Content-Disposition': f'attachment; filename="ai_analysis_{sku}.pdf"'}
    )