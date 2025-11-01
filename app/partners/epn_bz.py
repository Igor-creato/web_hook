import json
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException
from urllib.parse import parse_qs
import logging

from .base_partner import BasePartner

logger = logging.getLogger(__name__)

class EpnBzPartner(BasePartner):
    """Класс для работы с webhook'ами EPN.bz согласно официальной документации"""
    
    def __init__(self, secret_token: Optional[str] = None):
        super().__init__("EPN.bz", secret_token)
        logger.info(f"EPN.bz partner initialized with token: {'Yes' if secret_token else 'No'}")
        
    async def verify_secret_token(self, provided_token: str) -> bool:
        """Проверка секретного токена из пути URL для EPN.bz"""
        try:
            is_valid = self.verify_path_secret_token(provided_token)
            
            if is_valid:
                logger.info(f"EPN.bz token verification successful")
            else:
                logger.warning(f"EPN.bz token verification failed")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying EPN.bz token: {e}")
            return False
    
    async def parse_webhook(self, request: Request, body: bytes) -> Dict[str, Any]:
        """Парсинг webhook'а от EPN.bz согласно документации"""
        try:
            client_ip = self.get_client_ip(request)
            user_agent = request.headers.get("user-agent", "")
            content_type = request.headers.get("content-type", "")
            
            if request.method == "POST":
                if "application/json" in content_type:
                    # JSON payload
                    data = json.loads(body.decode('utf-8'))
                    logger.info("Parsed EPN.bz JSON data")
                elif "application/x-www-form-urlencoded" in content_type:
                    # Form data
                    form_data = parse_qs(body.decode('utf-8'))
                    data = {k: v[0] if len(v) == 1 else v for k, v in form_data.items()}
                    logger.info("Parsed EPN.bz form data")
                else:
                    try:
                        data = json.loads(body.decode('utf-8'))
                        logger.info("Parsed EPN.bz data as JSON fallback")
                    except:
                        raw_string = body.decode('utf-8')
                        data = {"raw_content": raw_string}
                        logger.info("Parsed EPN.bz data as raw string")
            else:
                # GET request - параметры в URL
                data = dict(request.query_params)
                logger.info("Parsed EPN.bz GET data")
            
            # Добавляем метаданные
            data["_client_ip"] = client_ip
            data["_user_agent"] = user_agent
            data["_method"] = request.method
            data["_content_type"] = content_type
            
            logger.info(f"Parsed EPN.bz data keys: {list(data.keys())}")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from EPN.bz: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        except Exception as e:
            logger.error(f"Error parsing EPN.bz webhook: {e}")
            raise HTTPException(status_code=400, detail="Failed to parse webhook data")
    
    async def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка и нормализация данных EPN.bz согласно документации"""
        try:
            # Обязательные поля согласно документации EPN.bz
            click_id = data.get("click_id")  # ID пользователя в нашей БД
            order_number = data.get("order_number")
            
            # Проверяем обязательные поля
            if not click_id:
                raise HTTPException(status_code=400, detail="Missing required field: click_id")
            if not order_number:
                raise HTTPException(status_code=400, detail="Missing required field: order_number")
            
            # Определяем тип события на основе order_status
            order_status = self._normalize_order_status(data.get("order_status"))
            event_type = self._determine_event_type(order_status)
            
            # Нормализация данных согласно документации EPN.bz
            processed_data = {
                "partner": "epn_bz",
                "event_type": event_type,
                
                # Обязательные поля EPN.bz
                "click_id": click_id,  # ID пользователя
                "order_number": order_number,
                "uniq_id": data.get("uniq_id", f"gen_{order_number}_{click_id}"),  # Генерируем если нет
                "order_status": order_status,
                
                # Необязательные поля EPN.bz
                "offer_name": data.get("offer_name"),
                "offer_type": data.get("offer_type"),
                "offer_id": data.get("offer_id"),
                "type_id": self._extract_int(data, "type_id"),
                "sub": data.get("sub"),
                "sub2": data.get("sub2"),
                "sub3": data.get("sub3"),
                "sub4": data.get("sub4"),
                "sub5": data.get("sub5"),
                "revenue": self._extract_amount(data, "revenue"),
                "commission_fee": self._extract_amount(data, "commission_fee"),
                "currency": data.get("currency", "RUB"),
                "ip": data.get("ip"),
                "ipv6": data.get("ipv6"),
                "user_agent_epn": data.get("user_agent"),  # UserAgent от EPN
                "click_time": data.get("click_time"),
                "time_of_order": data.get("time_of_order"),
                
                # Технические поля
                "client_ip": data.get("_client_ip"),
                "user_agent": data.get("_user_agent"),  # UserAgent webhook запроса
                "raw_data": data
            }
            
            logger.info(f"Processed EPN.bz data: uniq_id={processed_data['uniq_id']}, status={processed_data['order_status']}, revenue={processed_data['revenue']}, commission={processed_data['commission_fee']}")
            return processed_data
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing EPN.bz data: {e}")
            raise HTTPException(status_code=400, detail="Failed to process webhook data")
    
    def _normalize_order_status(self, status: Optional[str]) -> str:
        """Нормализация статуса заказа согласно документации EPN.bz"""
        if not status:
            return "unknown"
        
        status_lower = status.lower()
        
        # Возможные значения согласно документации EPN.bz:
        # waiting (новый заказ), pending (холд), completed (подтверждено), rejected (заказ отменен)
        if status_lower in ["waiting"]:
            return "waiting"
        elif status_lower in ["pending"]:
            return "pending"
        elif status_lower in ["completed", "confirmed", "approved"]:
            return "completed"
        elif status_lower in ["rejected", "cancelled", "canceled", "declined"]:
            return "rejected"
        else:
            logger.warning(f"Unknown EPN.bz order status: {status}")
            return status_lower
    
    def _determine_event_type(self, order_status: str) -> str:
        """Определение типа события на основе статуса"""
        if order_status == "waiting":
            return "order.created"
        elif order_status == "pending":
            return "order.pending"
        elif order_status == "completed":
            return "order.completed"
        elif order_status == "rejected":
            return "order.rejected"
        else:
            return "order.unknown"
    
    def _extract_amount(self, data: Dict[str, Any], field: str) -> float:
        """Безопасное извлечение суммы"""
        try:
            value = data.get(field, 0)
            if value is None or value == '':
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Failed to convert {field}={data.get(field)} to float")
            return 0.0
    
    def _extract_int(self, data: Dict[str, Any], field: str) -> Optional[int]:
        """Безопасное извлечение целого числа"""
        try:
            value = data.get(field)
            if value is None or value == '':
                return None
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Failed to convert {field}={data.get(field)} to int")
            return None
    
    async def validate_request(self, request: Request) -> bool:
        """Дополнительная валидация для EPN.bz"""
        client_ip = self.get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        logger.info(f"EPN.bz request validation: IP={client_ip}, UA={user_agent[:50]}...")
        
        return True