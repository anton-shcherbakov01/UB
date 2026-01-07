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

@app.get("/api/analyze/{sku}")
async def analyze_product(sku: int, x_tg_data: str = Header(None)):
    # Проверка Telegram (можно раскомментировать для продакшена)
    # if not auth_manager.validate_init_data(x_tg_data):
    #     raise HTTPException(status_code=401, detail="Unauthorized")

    result = parser_service.get_product_data(sku)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    
    return analysis_service.calculate_metrics(result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)