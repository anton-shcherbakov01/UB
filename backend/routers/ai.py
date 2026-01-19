import os
import io
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fpdf import FPDF

from database import get_db, User, SearchHistory
from dependencies import get_current_user
from dependencies.quota import QuotaCheck, increment_usage
from services.queue_service import queue_service
from tasks import analyze_reviews_task, get_status
# Используем parser_service, который правильно работает с async
from parser_service import parser_service

logger = logging.getLogger("AI-Router")
router = APIRouter(prefix="/api", tags=["AI"])

@router.get("/ai/check/{sku}")
async def check_product_reviews(sku: int, user: User = Depends(get_current_user)):
    """
    Быстрый чек товара: возвращает название, фото и доступное кол-во отзывов.
    Нужен для настройки ползунка на фронте перед запуском анализа.
    """
    try:
        # Используем async метод через parser_service
        info = await parser_service.get_review_stats(sku)
        if not info:
            raise HTTPException(status_code=404, detail="Товар не найден или данные недоступны")
        if info.get("status") == "error":
            error_msg = info.get("message", "Ошибка при получении данных о товаре")
            logger.warning(f"Product check error for SKU {sku}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Check error for SKU {sku}: {e}", exc_info=True)
        # Возвращаем более понятное сообщение об ошибке
        error_message = "Не удалось проверить товар. Попробуйте позже или проверьте правильность артикула."
        raise HTTPException(status_code=500, detail=error_message)

@router.post("/ai/analyze/{sku}")
async def start_ai_analysis(
    sku: int, 
    limit: int = Query(100, ge=10, description="Max reviews to parse"),
    user: User = Depends(QuotaCheck("ai_requests")),
    db: AsyncSession = Depends(get_db)
):
    """
    Start AI analysis of product reviews.
    Requires ai_requests quota.
    """
    try:
        # Проверка доступности Celery и создание задачи с обработкой ошибок
        task = None
        try:
            task = analyze_reviews_task.delay(sku, limit, user.id)
            if not task:
                raise HTTPException(status_code=500, detail="Не удалось создать задачу анализа: задача не создана")
            if not task.id or not isinstance(task.id, str):
                raise HTTPException(status_code=500, detail="Не удалось создать задачу анализа: невалидный task_id")
        except HTTPException:
            raise
        except Exception as celery_error:
            logger.error(f"Celery task creation failed for SKU {sku}, user {user.id}: {celery_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка запуска анализа: {str(celery_error)}")
        
        # Add task to queue and get position (with error handling)
        queue_info = {
            "queue": "normal",
            "position": 0,
            "is_priority": False
        }
        try:
            queue_info = queue_service.add_task_to_queue(
                task_id=task.id,
                user_id=user.id,
                user_plan=user.subscription_plan,
                task_type="ai_analysis"
            )
        except Exception as queue_error:
            logger.warning(f"Queue service error (non-critical): {queue_error}")
            # Continue without queue info if queue service fails
        
        # Только после успешного создания задачи списываем квоту
        try:
            await increment_usage(user, "ai_requests", amount=1, db=db)
        except Exception as usage_error:
            logger.error(f"Failed to increment usage for user {user.id}: {usage_error}", exc_info=True)
            # Не прерываем выполнение, но логируем ошибку
        
        return {
            "status": "accepted", 
            "task_id": task.id,
            "queue": queue_info.get("queue", "normal"),
            "position": queue_info.get("position", 0),
            "is_priority": queue_info.get("is_priority", False)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting AI analysis for SKU {sku}, user {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка запуска анализа: {str(e)}")

@router.get("/ai/queue/{task_id}")
async def get_queue_position(
    task_id: str,
    user: User = Depends(get_current_user)
):
    """Get current position of task in queue"""
    position_info = queue_service.get_task_position(task_id, user.id)
    if position_info:
        return position_info
    return {"position": None, "status": "processing_or_completed"}

@router.get("/ai/result/{task_id}")
def get_ai_result(task_id: str):
    return get_status(task_id)

@router.get("/report/ai-pdf/{sku}")
async def generate_ai_pdf(sku: int, user: User = Depends(QuotaCheck(feature_flag="pnl_full")), db: AsyncSession = Depends(get_db)):

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

    # Шрифт (заглушка для примера, в проде нужны реальные пути)
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