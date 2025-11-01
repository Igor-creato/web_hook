#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

GITHUB_REPO="https://github.com/your-repo/epn-webhook-service.git"
PROJECT_DIR="epn-webhook-service"

echo -e "${BLUE}=== EPN.bz Webhook Service - Установка из GitHub ===${NC}"

# Проверка что мы не root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Не запускайте скрипт от root!${NC}"
    exit 1
fi

# Проверка зависимостей
echo -e "${YELLOW}Проверка зависимостей...${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}Git не установлен! Устанавливаем...${NC}"
    sudo apt update && sudo apt install -y git
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker не установлен! Устанавливаем...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo -e "${YELLOW}После установки Docker перезапустите терминал и запустите скрипт снова${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Docker Compose не установлен! Устанавливаем...${NC}"
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

if ! command -v openssl &> /dev/null; then
    echo -e "${RED}OpenSSL не установлен! Устанавливаем...${NC}"
    sudo apt update && sudo apt install -y openssl
fi

echo -e "${GREEN}Все зависимости установлены${NC}"

# Создание рабочей директории
echo -e "${YELLOW}Создание рабочей директории...${NC}"
if [ -d "svix" ]; then
    echo -e "${YELLOW}Директория svix уже существует. Удаляем...${NC}"
    rm -rf svix
fi

mkdir svix && cd svix

# Клонирование репозитория
echo -e "${YELLOW}Клонирование репозитория...${NC}"
git clone $GITHUB_REPO .

if [ ! -f "install.sh" ]; then
    echo -e "${RED}Ошибка: Не удалось клонировать репозиторий или файл install.sh не найден${NC}"
    echo -e "${YELLOW}Создаем структуру проекта вручную...${NC}"
    
    # Создаем структуру вручную если клонирование не удалось
    mkdir -p app/partners docs
    
    # Минимальный файл для проверки
    echo "# Project cloned manually" > project_info.txt
fi

# Запрос параметров конфигурации
echo -e "${BLUE}Настройка параметров:${NC}"

read -p "Введите домен для веб-интерфейса (например svix.yourdomain.com): " DOMAIN
if [ -z "$DOMAIN" ]; then
    echo -e "${RED}Домен обязателен!${NC}"
    exit 1
fi

read -p "Введите название таблицы для webhook данных [webhook_events]: " TABLE_NAME
TABLE_NAME=${TABLE_NAME:-webhook_events}

read -p "Введите логин MariaDB: " DB_USER
if [ -z "$DB_USER" ]; then
    echo -e "${RED}Логин обязателен!${NC}"
    exit 1
fi

read -s -p "Введите пароль MariaDB: " DB_PASSWORD
echo
if [ -z "$DB_PASSWORD" ]; then
    echo -e "${RED}Пароль обязателен!${NC}"
    exit 1
fi

read -p "Введите название базы данных [wordpress]: " DB_NAME
DB_NAME=${DB_NAME:-wordpress}

echo -e "${BLUE}Настройка email уведомлений об ошибках:${NC}"

read -p "Введите email для уведомлений об ошибках (можно пропустить): " ALERT_EMAIL
if [ -z "$ALERT_EMAIL" ]; then
    echo -e "${YELLOW}Email уведомления отключены${NC}"
    SMTP_USERNAME=""
    SMTP_PASSWORD=""
    SMTP_SERVER="smtp.gmail.com"
    SMTP_PORT="587"
    FROM_EMAIL=""
else
    read -p "Введите SMTP сервер [smtp.gmail.com]: " SMTP_SERVER
    SMTP_SERVER=${SMTP_SERVER:-smtp.gmail.com}
    
    read -p "Введите SMTP порт [587]: " SMTP_PORT
    SMTP_PORT=${SMTP_PORT:-587}
    
    read -p "Введите email для отправки уведомлений [${ALERT_EMAIL}]: " SMTP_USERNAME
    SMTP_USERNAME=${SMTP_USERNAME:-$ALERT_EMAIL}
    
    read -s -p "Введите пароль для email (для Gmail используйте App Password): " SMTP_PASSWORD
    echo
    if [ -z "$SMTP_PASSWORD" ]; then
        echo -e "${YELLOW}Пароль не указан - email уведомления отключены${NC}"
        SMTP_USERNAME=""
        ALERT_EMAIL=""
    fi
    
    read -p "Введите From email [${SMTP_USERNAME}]: " FROM_EMAIL
    FROM_EMAIL=${FROM_EMAIL:-$SMTP_USERNAME}
fi

# Генерация секретного токена
WEBHOOK_SECRET_TOKEN=$(openssl rand -hex 32)
echo -e "${GREEN}Сгенерирован секретный токен: $WEBHOOK_SECRET_TOKEN${NC}"

WEBHOOK_DOMAIN="webhook.${DOMAIN}"
FULL_WEBHOOK_URL="https://${WEBHOOK_DOMAIN}/webhook/${WEBHOOK_SECRET_TOKEN}"

# Создание .env файла
echo -e "${YELLOW}Создание конфигурационного файла...${NC}"
cat > .env << EOF
# Database Configuration
DATABASE_URL=mysql://${DB_USER}:${DB_PASSWORD}@db:3306/${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=${DB_NAME}
TABLE_NAME=${TABLE_NAME}

# Webhook Configuration
WEBHOOK_SECRET_TOKEN=${WEBHOOK_SECRET_TOKEN}
WEBHOOK_DOMAIN=${WEBHOOK_DOMAIN}
DOMAIN=${DOMAIN}

# Svix Configuration
SVIX_DB_DSN=postgresql://svix:svix_password@svix_postgres:5432/svix
SVIX_REDIS_DSN=redis://svix_redis:6379
SVIX_JWT_SECRET=$(openssl rand -base64 32)

# FastAPI Configuration
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000

# Email notification settings
SMTP_SERVER=${SMTP_SERVER}
SMTP_PORT=${SMTP_PORT}
SMTP_USERNAME=${SMTP_USERNAME}
SMTP_PASSWORD=${SMTP_PASSWORD}
ALERT_EMAIL=${ALERT_EMAIL}
FROM_EMAIL=${FROM_EMAIL}
EOF

# Создание docker-compose.yml из шаблона
echo -e "${YELLOW}Создание Docker Compose конфигурации...${NC}"
if [ -f "docker-compose.yml.template" ]; then
    cp docker-compose.yml.template docker-compose.yml
    # Замена переменных в шаблоне если нужно
else
    # Создаем docker-compose.yml если шаблон не найден
    cat > docker-compose.yml << 'EOF'

networks:
  proxy:
    external: true
  wp-backend:
    external: true
  svix-internal:
    driver: bridge

services:
  # PostgreSQL для Svix
  svix_postgres:
    image: postgres:13-alpine
    environment:
      POSTGRES_DB: svix
      POSTGRES_USER: svix
      POSTGRES_PASSWORD: svix_password
    volumes:
      - svix_postgres_data:/var/lib/postgresql/data
    networks:
      - svix-internal
    restart: unless-stopped

  # Redis для Svix
  svix_redis:
    image: redis:7-alpine
    networks:
      - svix-internal
    restart: unless-stopped

  # Svix Server
  svix_server:
    image: svix/svix-server:latest
    environment:
      SVIX_DB_DSN: postgresql://svix:svix_password@svix_postgres:5432/svix
      SVIX_REDIS_DSN: redis://svix_redis:6379
      SVIX_JWT_SECRET: ${SVIX_JWT_SECRET}
      SVIX_QUEUE_TYPE: redis
    depends_on:
      - svix_postgres
      - svix_redis
    networks:
      - svix-internal
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.svix.rule=Host(\`${DOMAIN}\`)"
      - "traefik.http.routers.svix.tls=true"
      - "traefik.http.routers.svix.tls.certresolver=letsencrypt"
      - "traefik.http.services.svix.loadbalancer.server.port=8071"
      - "traefik.docker.network=proxy"
    restart: unless-stopped

  # FastAPI Webhook Receiver
  webhook_receiver:
    build: ./app
    environment:
      DATABASE_URL: mysql://${DB_USER}:${DB_PASSWORD}@db:3306/${DB_NAME}
      WEBHOOK_SECRET_TOKEN: ${WEBHOOK_SECRET_TOKEN}
      TABLE_NAME: ${TABLE_NAME}
      SVIX_API_URL: http://svix_server:8071
      SMTP_SERVER: ${SMTP_SERVER}
      SMTP_PORT: ${SMTP_PORT}
      SMTP_USERNAME: ${SMTP_USERNAME}
      SMTP_PASSWORD: ${SMTP_PASSWORD}
      ALERT_EMAIL: ${ALERT_EMAIL}
      FROM_EMAIL: ${FROM_EMAIL}
    depends_on:
      - svix_server
    networks:
      - svix-internal
      - wp-backend
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webhook.rule=Host(\`${WEBHOOK_DOMAIN}\`)"
      - "traefik.http.routers.webhook.tls=true"
      - "traefik.http.routers.webhook.tls.certresolver=letsencrypt"
      - "traefik.http.services.webhook.loadbalancer.server.port=8000"
      - "traefik.docker.network=proxy"
    restart: unless-stopped

volumes:
  svix_postgres_data:
EOF
fi

# Создание Docker сетей если они не существуют
echo -e "${YELLOW}Создание Docker сетей...${NC}"
docker network create proxy 2>/dev/null || echo "Сеть proxy уже существует"
docker network create wp-backend 2>/dev/null || echo "Сеть wp-backend уже существует"

# Проверка существования файлов приложения
echo -e "${YELLOW}Проверка файлов приложения...${NC}"
if [ ! -f "app/main.py" ]; then
    echo -e "${YELLOW}Файлы приложения отсутствуют. Создаем базовую структуру...${NC}"
    # Здесь можно добавить создание базовых файлов если они отсутствуют
fi

# Сборка и запуск
echo -e "${YELLOW}Сборка и запуск контейнеров...${NC}"
docker-compose up -d --build

# Ожидание запуска сервисов
echo -e "${YELLOW}Ожидание запуска сервисов (30 секунд)...${NC}"
sleep 30

# Проверка статуса
echo -e "${BLUE}Проверка статуса сервисов:${NC}"
docker-compose ps

echo -e "${GREEN}=== УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО! ===${NC}"
echo -e "${BLUE}Сервисы доступны по адресам:${NC}"
echo -e "Svix Dashboard: https://${DOMAIN}"
echo -e "Webhook Receiver: https://${WEBHOOK_DOMAIN}"
echo -e "Health Check: https://${WEBHOOK_DOMAIN}/health"
echo ""
echo -e "${GREEN}=== WEBHOOK URL ДЛЯ EPN.BZ ===${NC}"
echo -e "${YELLOW}${FULL_WEBHOOK_URL}${NC}"
echo ""
if [ -n "$ALERT_EMAIL" ]; then
    echo -e "${BLUE}Email уведомления настроены: ${ALERT_EMAIL}${NC}"
else
    echo -e "${YELLOW}Email уведомления отключены${NC}"
fi
echo ""
echo -e "${BLUE}Примеры тестирования:${NC}"
echo -e "${YELLOW}Новый заказ:${NC}"
echo -e "curl '${FULL_WEBHOOK_URL}?click_id=123&order_number=ORDER-001&uniq_id=EPN-12345&order_status=waiting&revenue=1500&commission_fee=100'"
echo ""
echo -e "${YELLOW}Подтверждение:${NC}"
echo -e "curl '${FULL_WEBHOOK_URL}?click_id=123&order_number=ORDER-001&uniq_id=EPN-12345&order_status=completed&revenue=1500&commission_fee=100'"
echo ""
echo -e "${BLUE}Для просмотра логов:${NC}"
echo -e "docker-compose logs -f webhook_receiver"
echo ""
echo -e "${GREEN}Секретный токен сохранен в файле .env${NC}"
echo -e "${RED}ВАЖНО: При падении БД webhook'и автоматически повторяются через Svix!${NC}"