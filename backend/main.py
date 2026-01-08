import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from parser_service import parser_service
from analysis_service import analysis_service
from auth_service import AuthService

# Инициализация окружения
load_dotenv()

app = FastAPI(title="WB Microservice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_manager = AuthService(os.getenv("BOT_TOKEN"))

# Убираем async, чтобы FastAPI запускал парсинг в пуле потоков
# Это позволит обрабатывать несколько запросов параллельно
@app.get("/api/analyze/{sku}")
def analyze_product(sku: int, x_tg_data: str = Header(None)):
    """
    Эндпоинт анализа товара. 
    Использует блокирующий вызов парсера в отдельном потоке (Thread Pool).
    """
    result = parser_service.get_product_data(sku)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    
    return analysis_service.calculate_metrics(result)

if __name__ == "__main__":
    import uvicorn
    # Увеличиваем лимиты таймаута для uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=300)