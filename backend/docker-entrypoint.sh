#!/bin/bash
set -e

# Функция ожидания доступности порта (простая реализация на bash)
wait_for_port() {
  local host="$1"
  local port="$2"
  local timeout=30
  local start_time=$(date +%s)

  echo "⏳ Waiting for $host:$port..."
  while ! nc -z "$host" "$port" >/dev/null 2>&1; do
    sleep 1
    local current_time=$(date +%s)
    if (( current_time - start_time > timeout )); then
      echo "❌ Timeout waiting for $host:$port"
      return 1
    fi
  done
  echo "✅ $host:$port is available"
}

# Ждем базу данных (хост db, порт 5432)
# Используем python-скрипт или просто попытку миграции для надежности,
# но здесь просто запускаем миграцию, она сама упадет/повторит если что.

echo "🚀 Running migrations..."
python migrate.py

# Запускаем основную команду (переданную из Dockerfile или docker-compose)
echo "🔥 Starting command: $@"
exec "$@"