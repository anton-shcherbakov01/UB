FROM python:3.9-slim

# 1. Установка системных утилит, ШРИФТОВ (fonts-dejavu) и самого БРАУЗЕРА Edge
# fonts-dejavu — решает проблему с квадратиками в PDF
# microsoft-edge-stable — сам браузер, который нужен для Selenium
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl fontconfig fonts-dejavu \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list \
    && apt-get update && apt-get install -y microsoft-edge-stable \
    && apt-get clean

# 2. Копируем ВАШ ЛОКАЛЬНЫЙ драйвер (который вы положили в папку backend)
# Никаких скачиваний с Azure/Microsoft, берем файл с диска
COPY msedgedriver /usr/local/bin/msedgedriver
RUN chmod +x /usr/local/bin/msedgedriver

# 3. Настройка приложения Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]