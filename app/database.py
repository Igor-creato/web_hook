import os
import logging
from typing import Dict, Any, Optional
import pymysql
from datetime import datetime
import json

class DatabaseConnectionError(Exception):
    pass

class DatabaseOperationError(Exception):
    pass


logger = logging.getLogger(__name__)

# Настройки подключения к базе данных
DATABASE_URL = os.getenv("DATABASE_URL")
TABLE_NAME = os.getenv("TABLE_NAME", "webhook_events")

def get_db_connection():
    """Получение соединения с MariaDB"""
    try:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not configured")
        
        parts = DATABASE_URL.replace("mysql://", "").split("/")
        db_name = parts if len(parts) > 1 else "wordpress"
        auth_host = parts.split("@")
        host_port = auth_host.split(":")
        host = host_port
        port = int(host_port) if len(host_port) > 1 else 3306
        user_pass = auth_host.split(":")
        user = user_pass
        password = user_pass
        
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        
        return connection
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None

async def init_db():
    """Инициализация базы данных с правильной структурой для EPN.bz"""
    try:
        connection = get_db_connection()
        if not connection:
            logger.error("Failed to connect to database for initialization")
            return
        
        with connection.cursor() as cursor:
            # Создание таблицы для webhook событий EPN.bz
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS `{TABLE_NAME}` (
                `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
                `partner` varchar(50) NOT NULL DEFAULT 'epn_bz' COMMENT 'Партнер (epn_bz, admitad, etc)',
                `event_type` varchar(100) NOT NULL COMMENT 'Тип события',
                
                -- EPN.bz обязательные поля
                `click_id` varchar(255) NOT NULL COMMENT 'ID пользователя из click_id',
                `order_number` varchar(255) NOT NULL COMMENT 'Номер заказа (уникален в рамках оффера)',
                `uniq_id` varchar(255) NOT NULL COMMENT 'Уникальный идентификатор заказа в ePN',
                `order_status` varchar(50) NOT NULL COMMENT 'Статус заказа (waiting/pending/completed/rejected)',
                
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
                
                PRIMARY KEY (`id`),
                -- ИСПРАВЛЕННАЯ УНИКАЛЬНОСТЬ: partner + uniq_id + order_status
                -- Это позволяет одному заказу иметь разные статусы (waiting -> completed -> rejected)
                UNIQUE KEY `unique_partner_uniq_status` (`partner`, `uniq_id`, `order_status`),
                
                -- Индексы для оптимизации
                KEY `idx_partner_status` (`partner`, `order_status`),
                KEY `idx_created_at` (`created_at`),
                KEY `idx_uniq_id` (`uniq_id`),
                KEY `idx_click_id` (`click_id`),
                KEY `idx_order_number` (`order_number`),
                KEY `idx_partner_created` (`partner`, `created_at`),
                KEY `idx_revenue_commission` (`revenue`, `commission_fee`),
                KEY `idx_event_type` (`event_type`),
                KEY `idx_offer_id` (`offer_id`)
                
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            COMMENT='Таблица для хранения событий от EPN.bz с правильной уникальностью'
            """
            
            cursor.execute(create_table_sql)
            logger.info(f"Table {TABLE_NAME} created or already exists with correct EPN.bz structure")
        
        connection.close()
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

async def save_webhook_event(data: Dict[str, Any]) -> bool:
    """Сохранение события webhook в базу данных с правильной логикой EPN.bz"""
    try:
        connection = get_db_connection()
        if not connection:
            logger.error("Failed to connect to database for saving")
            return False
        
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
            
            # Подготовка данных
            insert_data = {
                'partner': data.get('partner', 'epn_bz'),
                'event_type': data.get('event_type'),
                'click_id': data.get('click_id'),
                'order_number': data.get('order_number'),
                'uniq_id': data.get('uniq_id'),
                'order_status': data.get('order_status'),
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
    except Exception as e:
        logger.error(f"Error saving webhook event: {e}")
        if "Duplicate entry" in str(e):
            logger.info("Duplicate webhook event (same uniq_id + status) - updated existing record")
            return True
        return False
