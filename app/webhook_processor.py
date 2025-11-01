import logging
import os
from typing import Dict, Any
from fastapi import Request, HTTPException, BackgroundTasks

from partners.base_partner import BasePartner
from database import save_webhook_event, DatabaseConnectionError, DatabaseOperationError

logger = logging.getLogger(__name__)

class WebhookProcessor:
    """Основной процессор webhook'ов с поддержкой секрета в пути URL и обработкой ошибок БД"""
    
    def __init__(self):
        self.partners: Dict[str, BasePartner] = {}
        self.secret_token = os.getenv("WEBHOOK_SECRET_TOKEN")
        logger.info("WebhookProcessor initialized with database error handling")
    
    def register_partner(self, partner_id: str, partner: BasePartner):
        """Регистрация нового партнера"""
        self.partners[partner_id] = partner
        logger.info(f"Registered partner: {partner_id}")
    
    async def process_webhook_with_path_secret(
        self, 
        secret_token: str,
        request: Request, 
        background_tasks: BackgroundTasks
    ):
        """Обработка webhook'а с проверкой секрета в пути URL и обработкой ошибок БД"""
        start_time = None
        processed_data = None
        
        try:
            import time
            start_time = time.time()
            
            # Проверка секретного токена
            if not self.secret_token:
                logger.error("Webhook secret token not configured")
                raise HTTPException(status_code=500, detail="Service configuration error")
            
            if secret_token != self.secret_token:
                logger.error(f"Invalid secret token provided: {secret_token[:8]}...")
                raise HTTPException(status_code=401, detail="Invalid secret token")
            
            logger.info(f"Valid secret token provided, processing webhook ({request.method})")
            
            # Определяем партнера (пока используем epn_bz по умолчанию)
            partner_id = self._determine_partner(request)
            
            if partner_id not in self.partners:
                logger.error(f"Unknown partner: {partner_id}")
                raise HTTPException(status_code=404, detail=f"Partner {partner_id} not supported")
            
            partner = self.partners[partner_id]
            logger.info(f"Processing webhook for partner: {partner_id}")
            
            # Получение тела запроса
            body = await request.body()
            
            # Валидация запроса
            if not await partner.validate_request(request):
                logger.error(f"Request validation failed for {partner_id}")
                raise HTTPException(status_code=400, detail="Request validation failed")
            
            # Дополнительная проверка токена через партнера
            if not await partner.verify_secret_token(secret_token):
                logger.error(f"Partner token verification failed for {partner_id}")
                raise HTTPException(status_code=401, detail="Token verification failed")
            
            # Парсинг данных
            raw_data = await partner.parse_webhook(request, body)
            
            # Обработка данных
            processed_data = await partner.process_data(raw_data)
            
            # Попытка сохранения в базу данных с обработкой ошибок
            try:
                # Сразу пытаемся сохранить синхронно для проверки доступности БД
                await save_webhook_event(processed_data)
                
                processing_time = time.time() - start_time if start_time else 0
                logger.info(f"Successfully processed and saved webhook for {partner_id} in {processing_time:.3f}s")
                
                return {
                    "status": "success",
                    "partner": partner_id,
                    "click_id": processed_data.get("click_id"),
                    "uniq_id": processed_data.get("uniq_id"),
                    "order_status": processed_data.get("order_status"),
                    "revenue": processed_data.get("revenue"),
                    "commission_fee": processed_data.get("commission_fee"),
                    "processing_time": f"{processing_time:.3f}s",
                    "message": "EPN.bz webhook processed and saved successfully",
                    "database_status": "healthy"
                }
                
            except DatabaseConnectionError as e:
                # Проблемы с подключением к БД - возвращаем 503 для retry
                processing_time = time.time() - start_time if start_time else 0
                logger.error(f"Database connection error after {processing_time:.3f}s: {e}")
                
                raise HTTPException(
                    status_code=503, 
                    detail="Database temporarily unavailable, please retry later"
                )
                
            except DatabaseOperationError as e:
                # Проблемы с операциями БД - тоже возвращаем 503 или 200 для дубликатов
                processing_time = time.time() - start_time if start_time else 0
                logger.error(f"Database operation error after {processing_time:.3f}s: {e}")
                
                # Проверяем, что это не дублирование записи
                if "Duplicate entry" in str(e):
                    logger.info("Duplicate webhook detected, treating as success")
                    return {
                        "status": "success",
                        "partner": partner_id,
                        "click_id": processed_data.get("click_id") if processed_data else "N/A",
                        "uniq_id": processed_data.get("uniq_id") if processed_data else "N/A", 
                        "order_status": processed_data.get("order_status") if processed_data else "N/A",
                        "processing_time": f"{processing_time:.3f}s",
                        "message": "Duplicate webhook - already processed",
                        "database_status": "duplicate_handled"
                    }
                else:
                    raise HTTPException(
                        status_code=503, 
                        detail="Database operation error, please retry later"
                    )
            
        except HTTPException:
            # Передаем HTTP ошибки как есть
            raise
        except Exception as e:
            processing_time = time.time() - start_time if start_time else 0
            logger.error(f"Unexpected error processing webhook after {processing_time:.3f}s: {e}")
            logger.error(f"Processed data: {processed_data}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    def _determine_partner(self, request: Request) -> str:
        """Определение партнера на основе запроса"""
        # Пока возвращаем epn_bz по умолчанию
        return "epn_bz"