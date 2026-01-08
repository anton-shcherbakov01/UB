import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
from celery_app import celery_app
from tasks import parse_sku_task
from dotenv import load_dotenv

# Импортируем сервисы для синхронного режима (совместимость)
from parser_service import parser_service
from analysis_service import analysis_service

load_dotenv()

app = FastAPI(title="WB Async Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- АСИНХРОННЫЕ ЭНДПОИНТЫ (Очереди) ---

@app.post("/api/monitor/add/{sku}")
async def add_to_queue(sku: int):
    """Добавить товар в очередь на парсинг"""
    task = parse_sku_task.delay(sku)
    return {
        "task_id": task.id, 
        "message": "Товар добавлен в очередь", 
        "queue_position": "Вычисляется..." 
    }

@app.get("/api/monitor/status/{task_id}")
async def get_task_status(task_id: str):
    """Узнать статус задачи"""
    task_result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": task_result.status,
    }

    if task_result.status == 'PENDING':
        response["info"] = "Ожидает свободного воркера"
    elif task_result.status == 'PROGRESS':
        response["info"] = task_result.info.get('status', 'В процессе...')
    elif task_result.status == 'SUCCESS':
        response["result"] = task_result.result
    elif task_result.status == 'FAILURE':
        response["error"] = str(task_result.result)

    return response

# --- СИНХРОННЫЙ ЭНДПОИНТ (СОВМЕСТИМОСТЬ) ---
# Этот метод нужен, чтобы старый фронтенд не получал 404

@app.get("/api/analyze/{sku}")
def analyze_product_sync(sku: int):
    """
    Старый метод для прямой проверки (блокирующий).
    Нужен для совместимости с текущим фронтендом.
    """
    # 1. Парсинг (прямой вызов, не через очередь)
    result = parser_service.get_product_data(sku)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    
    # 2. Анализ
    final_report = analysis_service.calculate_metrics(result)
        
    return final_report

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)