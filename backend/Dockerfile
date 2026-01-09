FROM python:3.9-slim

# 1. Установка системных утилит, ШРИФТОВ и Edge
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl fontconfig fonts-dejavu libpq-dev gcc \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list \
    && apt-get update && apt-get install -y microsoft-edge-stable \
    && apt-get clean

# 2. Драйвер (предполагаем, что файл лежит рядом с Dockerfile)
COPY msedgedriver /usr/local/bin/msedgedriver
RUN chmod +x /usr/local/bin/msedgedriver

# 3. Настройка окружения
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Копируем код (для продакшена, в dev перекроется volume)
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]