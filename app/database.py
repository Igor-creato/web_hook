import os
import logging
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from typing import Dict, Any, Optional
import pymysql
from datetime import datetime
import json
import traceback
import asyncio

logger = logging.getLogger(__name__)

# Настройки подключения к базе данных
DATABASE_URL = os.getenv("DATABASE_URL")
TABLE_NAME = os.getenv("TABLE_NAME", "webhook_events")

# Настройки email уведомлений
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ALERT_EMAIL = os.getenv("ALERT_EMAIL")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USERNAME)

class DatabaseError(Exception):
    """Базовый класс для ошибок базы данных"""
    pass

class DatabaseConnectionError(DatabaseError):
    """Ошибка подключения к базе данных"""
    pass

class DatabaseOperationError(DatabaseError):
    """Ошибка выполнения операции в базе данных"""
    pass

def send_error_email(subject: str, error_message: str, webhook_data: Dict[str, Any] = None):
    """Отправка email уведомления об ошибке"""
    try:
        if not all([SMTP_USERNAME, SMTP_PASSWORD, ALERT_EMAIL]):
            logger.warning("Email settings not configured, skipping email notification")
            return False

        msg = MimeMultipart()
        msg['From'] = FROM_EMAIL or SMTP_USERNAME
        msg['To'] = ALERT_EMAIL
        msg['Subject'] = f"[Webhook Service Alert] {subject}"

        body = f"""
Произошла ошибка в сервисе приема webhook'ов:

Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Ошибка: {error_message}

"""
        
        if webhook_data:
            body += f"""
Данные webhook'а:
Partner: {webhook_data.get('partner', 'N/A')}
Event Type: {webhook_data.get('event_type', 'N/A')}
Uniq ID: {webhook_data.get('uniq_id', 'N/A')}
Order Status: {webhook_data.get('order_status', 'N/A')}
Revenue: {webhook_data.get('revenue', 'N/A')}
Commission: {webhook_data.get('commission_fee', 'N/A')}
Click ID: {webhook_data.get('click_id', 'N/A')}
Client IP: {webhook_data.get('client_ip', 'N/A')}

Raw Data: {json.dumps(webhook_data.get('raw_data', {}), indent=2, ensure_ascii=False)}
"""

        msg.attach(MimeText(body, 'plain', 'utf-8'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            
        logger.info(f"Error notification email sent to {ALERT_EMAIL}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send error notification email: {e}")
        return False

def get_db_connection():
    """Получение соединения с MariaDB с обработкой ошибок"""
    try:
        if not DATABASE_URL:
            raise DatabaseConnectionError("DATABASE_URL not configured")
        
        # Парсинг DATABASE_URL
        # Формат: mysql://user:password@host:port/database
        url_without_scheme = DATABASE_URL.replace("mysql://", "")
        
        # Разделяем на части
        if "@" not in url_without_scheme:
            raise DatabaseConnectionError("Invalid DATABASE_URL format: missing credentials")
            
        credentials_part, host_db_part = url_without_scheme.split("@", 1)
        
        if ":" not in credentials_part:
            raise DatabaseConnectionError("Invalid DATABASE_URL format: missing password")
            
        username, password = credentials_part.split(":", 1)
        
        # Парсим host:port/database
        if "/" not in host_db_part:
            raise DatabaseConnectionError("Invalid DATABASE_URL format: missing database name")
            
        host_port_part, database = host_db_part.split("/", 1)
        
        if ":" in host_port_part:
            host, port_str = host_port_part.split(":", 1)
            port = int(port_str)
        else:
            host = host_port_part
            port = 3306
        
        logger.info(f"Connecting to database: {host}:{port}/{database} as {username}")
        
        connection = pymysql.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            database=database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=30,  # Увеличили таймаут
            read_timeout=60      # Увеличили таймаут
        )
        
        # Тестируем соединение
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            logger.info("Database connection test successful")
        
        return connection
        
    except pymysql.MySQLError as e:
        error_code = e.args[0] if e.args else 0
        error_msg = str(e)
        
        logger.error(f"MySQL error {error_code}: {error_msg}")
        
        # Классификация ошибок
        if error_code in [2003, 2002, 2005, 2006, 2013]:  # Connection errors
            raise DatabaseConnectionError(f"Cannot connect to database: {error_msg}")
        elif error_code in [1045]:  # Access denied
            raise DatabaseConnectionError(f"Authentication failed: {error_msg}")
        elif error_code in [1049]:  # Unknown database
            raise DatabaseConnectionError(f"Database does not exist: {error_msg}")
        else:
            raise DatabaseOperationError(f"Database error: {error_msg}")
    except Exception as e:
        logger.error(f"Unexpected connection error: {str(e)}")
        raise DatabaseConnectionError(f"Unexpected connection error: {str(e)}")

async def init_db():
    """Инициализация базы данных с обработкой ошибок"""
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Database initialization attempt {attempt + 1}/{max_retries}")
            
            connection = get_db_connection()
            logger.info("Database connection established for initialization")
            
            with connection.cursor() as cursor:
                # Проверяем текущую базу данных
                cursor.execute("SELECT DATABASE()")
                current_db = cursor.fetchone()
                logger.info(f"Current database: {current_db}")
                
                # Создание таблицы для webhook событий EPN.bz
                create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS `{TABLE_NAME}` (
                    `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
                    `partner` varchar(50) NOT NULL DEFAULT 'epn_bz' COMMENT 'Партнер (epn_bz, admitad, etc)',
                    `event_type` varchar(100) NOT NULL DEFAULT 'unknown' COMMENT 'Тип события',
                    
                    -- EPN.bz обязательные поля
                    `click_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'ID пользователя из click_id',
                    `order_number` varchar(255) NOT NULL DEFAULT '' COMMENT 'Номер заказа (уникален в рамках оффера)',
                    `uniq_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'Уникальный идентификатор заказа в ePN',
                    `order_status` varchar(50) NOT NULL DEFAULT 'unknown' COMMENT 'Статус заказа (waiting/pending/completed/rejected)',
                    
                    -- EPN.bz необязательные поля
                    `offer_name` varchar(500) DEFAULT NULL COMMENT 'Название оффера в ePN',
                    `offer_type` varchar(100) DEFAULT NULL COMMENT 'Тег оффера в ePN',
                    `offer_id` varchar(255) DEFAULT NULL COMMENT 'ID оффера в системе ePN',
                    `type_id` int(11) DEFAULT NULL COMMENT 'Тип оффера (1-стандартные, 2-реферальные, 3-оффлайн)',
                    `sub` varchar(255) DEFAULT NULL COMMENT 'Sub1 переданный при переходе',
                    `sub2` varchar(255) DEFAULT NULL COMMENT 'Sub2 переданный при переходе',
                    `sub3` varchar(255) DEFAULT NULL COMMENT 'Sub3 переданный при переходе',
                    `sub4` varchar(255) DEFAULT NULL COMMENT 'Sub4 переданный при переходе',
                    `sub5` varchar(255) DEFAULT NULL COMMENT 'Sub5 переданный при переходе',
                    `revenue` decimal(15,2) DEFAULT 0.00 COMMENT 'Сумма покупки',
                    `commission_fee` decimal(15,2) DEFAULT 0.00 COMMENT 'Комиссия со сделки',
                    `currency` varchar(3) DEFAULT 'RUB' COMMENT 'Код валюты (RUB, USD, EUR, GBP, TON)',
                    `ip` varchar(45) DEFAULT NULL COMMENT 'IPv4 адрес перехода на оффер',
                    `ipv6` varchar(45) DEFAULT NULL COMMENT 'IPv6 адрес перехода на оффер',
                    `user_agent_epn` text COMMENT 'UserAgent зафиксированный при переходе в ePN',
                    `click_time` varchar(50) DEFAULT NULL COMMENT 'Время совершения клика (yyyy-mm-dd h:i:s)',
                    `time_of_order` varchar(50) DEFAULT NULL COMMENT 'Время появления заказа в системе ePN',
                    
                    -- Дополнительные технические поля
                    `client_ip` varchar(45) DEFAULT NULL COMMENT 'IP адрес webhook запроса',
                    `user_agent` text COMMENT 'User Agent webhook запроса',
                    `raw_data` json DEFAULT NULL COMMENT 'Исходные данные webhook',
                    `processed_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Время обработки',
                    `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Время создания',
                    `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Время обновления',
                    
                    PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
                  COMMENT='Таблица для хранения событий от EPN.bz с правильной уникальностью'
                """
                
                logger.info("Executing CREATE TABLE statement...")
                cursor.execute(create_table_sql)
                logger.info(f"Table {TABLE_NAME} created successfully")
                
                # Проверяем, что таблица действительно создалась
                cursor.execute(f"SHOW TABLES LIKE '{TABLE_NAME}'")
                table_exists = cursor.fetchone()
                
                if table_exists:
                    logger.info(f"✅ Table {TABLE_NAME} confirmed to exist")
                    
                    # Добавляем уникальный индекс отдельно для совместимости
                    try:
                        cursor.execute(f"""
                        ALTER TABLE `{TABLE_NAME}` 
                        ADD UNIQUE KEY `unique_partner_uniq_status` (`partner`, `uniq_id`, `order_status`)
                        """)
                        logger.info("✅ Unique index added successfully")
                    except pymysql.MySQLError as e:
                        if "Duplicate key name" in str(e):
                            logger.info("Unique index already exists, skipping")
                        else:
                            logger.warning(f"Could not add unique index: {e}")
                    
                    # Добавляем другие индексы
                    indexes = [
                        ("idx_partner_status", "(`partner`, `order_status`)"),
                        ("idx_created_at", "(`created_at`)"),
                        ("idx_uniq_id", "(`uniq_id`)"),
                        ("idx_click_id", "(`click_id`)"),
                        ("idx_order_number", "(`order_number`)"),
                        ("idx_partner_created", "(`partner`, `created_at`)"),
                        ("idx_revenue_commission", "(`revenue`, `commission_fee`)"),
                        ("idx_event_type", "(`event_type`)"),
                        ("idx_offer_id", "(`offer_id`)")
                    ]
                    
                    for index_name, index_columns in indexes:
                        try:
                            cursor.execute(f"ALTER TABLE `{TABLE_NAME}` ADD KEY `{index_name}` {index_columns}")
                            logger.info(f"✅ Index {index_name} added")
                        except pymysql.MySQLError as e:
                            if "Duplicate key name" in str(e):
                                logger.info(f"Index {index_name} already exists, skipping")
                            else:
                                logger.warning(f"Could not add index {index_name}: {e}")
                    
                    # Показываем структуру таблицы для подтверждения
                    cursor.execute(f"DESCRIBE `{TABLE_NAME}`")
                    columns = cursor.fetchall()
                    logger.info(f"Table structure confirmed - {len(columns)} columns:")
                    for col in columns[:5]:  # Показываем первые 5 колонок
                        logger.info(f"  - {col['Field']}: {col['Type']}")
                    
                else:
                    logger.error(f"❌ Table {TABLE_NAME} was not created!")
                    raise DatabaseOperationError(f"Table {TABLE_NAME} creation failed")
            
            connection.close()
            logger.info("✅ Database initialization completed successfully")
            return
            
        except DatabaseError as e:
            logger.error(f"Database error during initialization attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Экспоненциальный откат
            else:
                logger.error("All database initialization attempts failed")
                send_error_email("Database Initialization Failed", str(e))
                raise
        except Exception as e:
            logger.error(f"Unexpected error during database initialization attempt {attempt + 1}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error("All database initialization attempts failed")
                send_error_email("Database Initialization Unexpected Error", f"{str(e)}\\n\\nTraceback:\\n{traceback.format_exc()}")
                raise

async def save_webhook_event(data: Dict[str, Any]) -> bool:
    """Сохранение события webhook в базу данных с обработкой ошибок и email уведомлениями"""
    try:
        connection = get_db_connection()
        
        with connection.cursor() as cursor:
            # Подготовка данных для вставки
            insert_sql = f"""
            INSERT INTO `{TABLE_NAME}` 
            (partner, event_type, click_id, order_number, uniq_id, order_status,
             offer_name, offer_type, offer_id, type_id, sub, sub2, sub3, sub4, sub5,
             revenue, commission_fee, currency, ip, ipv6, user_agent_epn, 
             click_time, time_of_order, client_ip, user_agent, raw_data)
            VALUES 
            (%(partner)s, %(event_type)s, %(click_id)s, %(order_number)s, %(uniq_id)s, %(order_status)s,
             %(offer_name)s, %(offer_type)s, %(offer_id)s, %(type_id)s, %(sub)s, %(sub2)s, %(sub3)s, %(sub4)s, %(sub5)s,
             %(revenue)s, %(commission_fee)s, %(currency)s, %(ip)s, %(ipv6)s, %(user_agent_epn)s,
             %(click_time)s, %(time_of_order)s, %(client_ip)s, %(user_agent)s, %(raw_data)s)
            ON DUPLICATE KEY UPDATE
            event_type = VALUES(event_type),
            offer_name = VALUES(offer_name),
            offer_type = VALUES(offer_type),
            offer_id = VALUES(offer_id),
            type_id = VALUES(type_id),
            sub = VALUES(sub),
            sub2 = VALUES(sub2),
            sub3 = VALUES(sub3),
            sub4 = VALUES(sub4),
            sub5 = VALUES(sub5),
            revenue = VALUES(revenue),
            commission_fee = VALUES(commission_fee),
            currency = VALUES(currency),
            ip = VALUES(ip),
            ipv6 = VALUES(ipv6),
            user_agent_epn = VALUES(user_agent_epn),
            click_time = VALUES(click_time),
            time_of_order = VALUES(time_of_order),
            client_ip = VALUES(client_ip),
            user_agent = VALUES(user_agent),
            raw_data = VALUES(raw_data),
            updated_at = CURRENT_TIMESTAMP
            """
            
            # Подготовка данных с проверкой обязательных полей
            insert_data = {
                'partner': data.get('partner', 'epn_bz'),
                'event_type': data.get('event_type', 'unknown'),
                'click_id': data.get('click_id', ''),
                'order_number': data.get('order_number', ''),
                'uniq_id': data.get('uniq_id', ''),
                'order_status': data.get('order_status', 'unknown'),
                'offer_name': data.get('offer_name'),
                'offer_type': data.get('offer_type'),
                'offer_id': data.get('offer_id'),
                'type_id': data.get('type_id'),
                'sub': data.get('sub'),
                'sub2': data.get('sub2'),
                'sub3': data.get('sub3'),
                'sub4': data.get('sub4'),
                'sub5': data.get('sub5'),
                'revenue': data.get('revenue', 0),
                'commission_fee': data.get('commission_fee', 0),
                'currency': data.get('currency', 'RUB'),
                'ip': data.get('ip'),
                'ipv6': data.get('ipv6'),
                'user_agent_epn': data.get('user_agent_epn'),
                'click_time': data.get('click_time'),
                'time_of_order': data.get('time_of_order'),
                'client_ip': data.get('client_ip'),
                'user_agent': data.get('user_agent'),
                'raw_data': json.dumps(data.get('raw_data', {}), ensure_ascii=False)
            }
            
            cursor.execute(insert_sql, insert_data)
            
            logger.info(f"Saved EPN.bz webhook: partner={insert_data['partner']}, uniq_id={insert_data['uniq_id']}, status={insert_data['order_status']}, revenue={insert_data['revenue']} {insert_data['currency']}")
            
        connection.close()
        return True
        
    except DatabaseConnectionError as e:
        logger.error(f"Database connection error while saving webhook: {e}")
        send_error_email("Database Connection Error", str(e), data)
        raise  # Поднимаем ошибку для возврата 503
        
    except DatabaseOperationError as e:
        logger.error(f"Database operation error while saving webhook: {e}")
        send_error_email("Database Operation Error", str(e), data)
        
        # Некоторые операционные ошибки не требуют retry (например, дублирующие записи)
        if "Duplicate entry" in str(e):
            logger.info("Duplicate webhook event - this is expected behavior")
            return True
        else:
            raise  # Поднимаем для retry
            
    except Exception as e:
        logger.error(f"Unexpected error while saving webhook: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        send_error_email("Unexpected Database Error", f"{str(e)}\\n\\nTraceback:\\n{traceback.format_exc()}", data)
        raise  # Поднимаем для retry