import os
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Path
from fastapi.responses import JSONResponse
import logging
from contextlib import asynccontextmanager

from database import init_db
from webhook_processor import WebhookProcessor
from partners.epn_bz import EpnBzPartner

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение секретного токена из переменной окружения
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")

# Инициализация базы данных при старте
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")
    logger.info(f"Webhook secret token configured: {'Yes' if WEBHOOK_SECRET_TOKEN else 'No'}")
    yield
    # Shutdown
    logger.info("Shutting down...")

app = FastAPI(
    title="EPN.bz Webhook Service with Error Handling",
    description="Сервис приема webhook'ов от EPN.bz с обработкой ошибок БД и email уведомлениями",
    version="4.0.0",
    lifespan=lifespan
)

# Инициализация процессора webhook'ов
webhook_processor = WebhookProcessor()

# Регистрация партнеров с токеном
webhook_processor.register_partner("epn_bz", EpnBzPartner(WEBHOOK_SECRET_TOKEN))

@app.get("/")
async def root():
    webhook_domain = os.getenv("WEBHOOK_DOMAIN", "webhook.yourdomain.com")
    alert_email = os.getenv("ALERT_EMAIL", "Not configured")
    return {
        "message": "EPN.bz Webhook Service with Error Handling is running",
        "version": "4.0.0",
        "description": "Обработка ошибок БД + email уведомления + HTTP 503 для retry",
        "uniqueness": "partner + uniq_id + order_status",
        "error_handling": {
            "database_errors": "HTTP 503 + email notification + Svix retry",
            "email_alerts": alert_email,
            "duplicate_handling": "HTTP 200 OK (expected behavior)"
        },
        "endpoints": {
            "health": "/health",
            "webhook_url": f"https://{webhook_domain}/webhook/{{SECRET_TOKEN}}",
            "example": f"https://{webhook_domain}/webhook/{WEBHOOK_SECRET_TOKEN[:16]}..." if WEBHOOK_SECRET_TOKEN else "Not configured"
        },
        "epn_bz_fields": {
            "required": ["click_id", "order_number"],
            "optional": ["uniq_id", "order_status", "offer_name", "revenue", "commission_fee", "etc"]
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "service": "epn-bz-webhook-receiver-with-errors",
        "version": "4.0.0",
        "secret_configured": bool(WEBHOOK_SECRET_TOKEN),
        "email_configured": bool(os.getenv("ALERT_EMAIL"))
    }

@app.post("/webhook/{secret_token}")
async def receive_webhook_post(
    secret_token: str = Path(..., description="Секретный токен для аутентификации"),
    request: Request = None,
    background_tasks: BackgroundTasks = None
):
    """Прием POST webhook'ов от EPN.bz с обработкой ошибок БД"""
    return await webhook_processor.process_webhook_with_path_secret(
        secret_token, request, background_tasks
    )

@app.get("/webhook/{secret_token}")
async def receive_webhook_get(
    secret_token: str = Path(..., description="Секретный токен для аутентификации"),
    request: Request = None,
    background_tasks: BackgroundTasks = None
):
    """Прием GET webhook'ов от EPN.bz с обработкой ошибок БД"""
    return await webhook_processor.process_webhook_with_path_secret(
        secret_token, request, background_tasks
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )