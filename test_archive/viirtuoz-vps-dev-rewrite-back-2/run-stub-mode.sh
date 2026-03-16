#!/bin/bash
# Скрипт для быстрого запуска приложения в stub режиме (без Kubernetes)
#
# --with-db   Поднять PostgreSQL в Docker и подключить к приложению
#             (админка, пользователи, роли будут работать с реальной БД)

WITH_DB=false
for arg in "$@"; do
	case "$arg" in
		--with-db) WITH_DB=true ;;
	esac
done

echo "🚀 Запуск KubeVirt API Manager в STUB режиме (без Kubernetes)"
echo "=================================================="

# Порт для stub-режима (8080 по умолчанию, 8970 если 8080 занят)
STUB_PORT="${PORT:-8970}"
if command -v fuser >/dev/null 2>&1; then
	fuser -k 8970/tcp 2>/dev/null; fuser -k 8080/tcp 2>/dev/null
	sleep 2
fi
export PORT="$STUB_PORT"

# Установка переменных окружения
export FRONTEND_STUB_MODE=true
export DEBUG=true
export DEMO_USERNAME=admin
export DEMO_PASSWORD=your-secret-password
export SECRET_KEY=dev-secret-key-for-stub-mode
# LLM: задайте в .env
export LLM_SERVICE_URL="${LLM_SERVICE_URL}"
export LLM_CHAT_SHARED_TOKEN="${LLM_CHAT_SHARED_TOKEN}"
export LLM_MODEL="${LLM_MODEL}"
export LLM_AUTH_SERVICE_URL="${LLM_AUTH_SERVICE_URL}"
export LLM_AUTH_ADMIN_TOKEN="${LLM_AUTH_ADMIN_TOKEN}"
export LLM_USER_KEYS_MAX="${LLM_USER_KEYS_MAX:-10}"
export LLM_KEYS_ENCRYPTION_KEY="${LLM_KEYS_ENCRYPTION_KEY}"
if [ "$WITH_DB" = true ]; then
	COMPOSE_FILE="$(dirname "$0")/docker-compose.stub.yml"
	if [ ! -f "$COMPOSE_FILE" ]; then
		echo "❌ Файл $COMPOSE_FILE не найден"
		exit 1
	fi
	echo "📦 Запуск PostgreSQL..."
	if command -v docker >/dev/null 2>&1; then
		if docker compose version >/dev/null 2>&1; then
			DC="docker compose"
		else
			DC="docker-compose"
		fi
	else
		echo "❌ Docker не найден. Установите Docker для --with-db"
		exit 1
	fi
	$DC -f "$COMPOSE_FILE" up -d postgres
	echo "   Ожидание готовности PostgreSQL..."
	for i in {1..30}; do
		if $DC -f "$COMPOSE_FILE" exec -T postgres pg_isready -U viirtuoz 2>/dev/null; then
			break
		fi
		sleep 1
	done
	export DATABASE_URL="postgresql://viirtuoz:stub@127.0.0.1:5434/viirtuoz"
	export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
	export ADMIN_PASSWORD="${ADMIN_PASSWORD:-your-secret-password}"
	echo "✅ PostgreSQL запущен (порт 5434)"
	echo "   DATABASE_URL=postgresql://viirtuoz:***@127.0.0.1:5434/viirtuoz"
	echo "   Первый запуск создаст админа: $ADMIN_USERNAME / $ADMIN_PASSWORD"
	echo ""
else
	# Без БД: демо-режим с одним пользователем из env (переменная пустая — приоритет над .env)
	export DATABASE_URL=""
fi

echo "✅ Переменные окружения установлены:"
echo "   FRONTEND_STUB_MODE=true"
echo "   DEBUG=true"
echo "   DEMO_USERNAME=admin"
echo "   DEMO_PASSWORD=your-secret-password"
[ -n "${DATABASE_URL+x}" ] && echo "   DATABASE_URL=*** (реальная БД)"
[ -n "${LLM_AUTH_ADMIN_TOKEN}" ] && echo "   LLM_AUTH_ADMIN_TOKEN=*** (задан)"
[ -n "${LLM_CHAT_SHARED_TOKEN}" ] && echo "   LLM_CHAT_SHARED_TOKEN=*** (задан)"
echo ""

# Проверка зависимостей
if ! python3 -c "import fastapi" 2>/dev/null; then
	echo "❌ FastAPI не установлен"
	echo "   Установите зависимости: pip install -r requirements.txt"
	exit 1
fi

# Config: копируем example, если config.py отсутствует
if [ ! -f app/config.py ]; then
	if [ -f app/config.py.example ]; then
		cp app/config.py.example app/config.py
		echo "   app/config.py создан из example"
	fi
fi

echo "✅ Зависимости найдены"
echo ""

# Запуск приложения
echo "🌐 Запуск приложения..."
echo "   UI: http://localhost:$STUB_PORT"
echo "   Логин: admin / Пароль: your-secret-password"
echo "   LLM: чат использует общий токен из LLM_CHAT_SHARED_TOKEN"
echo ""
echo "📊 Демо VM: demo-gpu-vm, data-import-vm, analytics-vm"
[ "$WITH_DB" = true ] && echo "🗄️  С БД: docker compose -f docker-compose.stub.yml down — остановить PostgreSQL"
echo ""
echo "Нажмите Ctrl+C для остановки"
echo "=================================================="
echo ""

cd "$(dirname "$0")"
python3 -m app.main
