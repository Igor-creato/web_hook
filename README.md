Webhook Service
Надежный сервис для приема webhook'ов от EPN.bz с обработкой ошибок базы данных и email уведомлениями.
Установка 
```bash
curl -sSL https://raw.githubusercontent.com/Igor-creato/web_hook/main/install.sh | bash
```
Возможности
✅ HTTP 503 при ошибках БД - Svix автоматически повторяет отправку

✅ Email уведомления - Алерты при всех критических ошибках

✅ Правильная уникальность - (partner, uniq_id, order_status)

✅ Поддержка всех полей EPN.bz - Согласно официальной документации

✅ Обработка дубликатов - HTTP 200 OK для повторных webhook'ов

✅ Retry логика - До 5 попыток с экспоненциальным откатом

Быстрая установка
bash
curl -sSL https://raw.githubusercontent.com/your-repo/epn-webhook-service/main/install.sh | bash
Ручная установка
Клонируйте репозиторий:

bash
git clone https://github.com/your-repo/epn-webhook-service.git
cd epn-webhook-service
bash install.sh
Следуйте интерактивным инструкциям:

Укажите домен (например: svix.yourdomain.com)

Данные для подключения к MariaDB

Email для уведомлений об ошибках

SMTP настройки

После установки получите готовый URL:

text
https://webhook.yourdomain.com/webhook/SECRET_TOKEN
Структура проекта
text
epn-webhook-service/
├── README.md
├── install.sh # Скрипт установки
├── docker-compose.yml.template # Шаблон Docker Compose
├── app/
│ ├── Dockerfile
│ ├── requirements.txt
│ ├── main.py # FastAPI приложение
│ ├── database.py # Модуль базы данных с обработкой ошибок
│ ├── webhook_processor.py # Процессор webhook'ов
│ └── partners/
│ ├── **init**.py
│ ├── base_partner.py # Базовый класс партнера
│ └── epn_bz.py # Класс для EPN.bz
├── docs/
│ ├── DATABASE_ERROR_SCENARIOS.md
│ └── API.md
└── .env.example # Пример настроек
Поддерживаемые поля EPN.bz
Обязательные:
click_id - ID пользователя

order_number - Номер заказа

Статусы заказов:
waiting - Новый заказ

pending - Холд

completed - Подтверждено

rejected - Отменен

Финансовые поля:
revenue - Сумма покупки

commission_fee - Комиссия

currency - Валюта (RUB, USD, EUR, GBP, TON)

Примеры использования
Новый заказ
bash
curl 'https://webhook.yourdomain.com/webhook/SECRET_TOKEN?click_id=123&order_number=ORDER-001&uniq_id=EPN-12345&order_status=waiting&revenue=1500&commission_fee=100'
Подтверждение заказа
bash
curl 'https://webhook.yourdomain.com/webhook/SECRET_TOKEN?click_id=123&order_number=ORDER-001&uniq_id=EPN-12345&order_status=completed&revenue=1500&commission_fee=100'
Отмена заказа
bash
curl 'https://webhook.yourdomain.com/webhook/SECRET_TOKEN?click_id=123&order_number=ORDER-001&uniq_id=EPN-12345&order_status=rejected&revenue=1500&commission_fee=100'
Мониторинг
Health Check: https://webhook.yourdomain.com/health

Логи: docker-compose logs -f webhook_receiver

Email алерты: Автоматические при ошибках БД

Обработка ошибок
При недоступности базы данных:

⚠️ FastAPI возвращает HTTP 503

📧 Отправляется email администратору

🔄 Svix повторяет отправку webhook'а

✅ После восстановления БД webhook сохранится

🚫 Данные не теряются!

Технические детали
FastAPI - Современный Python веб-фреймворк

MariaDB - База данных для хранения webhook'ов

Svix - Надежная доставка webhook'ов

Redis - Очередь задач

Traefik - Reverse proxy с SSL

Поддержка
При возникновении проблем:

Проверьте логи: docker-compose logs -f

Проверьте статус: docker-compose ps

Проверьте health: curl https://webhook.yourdomain.com/health

Лицензия
MIT
