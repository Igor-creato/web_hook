from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from fastapi import Request
import logging

logger = logging.getLogger(__name__)

class BasePartner(ABC):
    """Базовый класс для всех партнеров"""
    
    def __init__(self, name: str, secret_token: Optional[str] = None):
        self.name = name
        self.secret_token = secret_token
        logger.info(f"Initialized partner: {name}")
    
    @abstractmethod
    async def verify_secret_token(self, provided_token: str) -> bool:
        """Проверка секретного токена из пути URL"""
        pass
    
    @abstractmethod
    async def parse_webhook(self, request: Request, body: bytes) -> Dict[str, Any]:
        """Парсинг данных webhook'а"""
        pass
    
    @abstractmethod
    async def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка и нормализация данных"""
        pass
    
    def get_client_ip(self, request: Request) -> str:
        """Получение IP клиента"""
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def verify_path_secret_token(self, provided_token: str) -> bool:
        """Базовая проверка токена из пути URL"""
        if not self.secret_token:
            logger.warning(f"No secret token configured for {self.name}")
            return True  # Пропускаем если токен не настроен
        
        if not provided_token:
            logger.warning(f"No token provided in URL path for {self.name}")
            return False
        
        is_valid = provided_token == self.secret_token
        logger.info(f"Token validation for {self.name}: {'Valid' if is_valid else 'Invalid'}")
        return is_valid
    
    async def validate_request(self, request: Request) -> bool:
        """Дополнительная валидация запроса"""
        return True