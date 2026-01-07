FROM python:3.9-slim

# Установка системных зависимостей для Edge и Selenium
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl \
    && curl [https://packages.microsoft.com/keys/microsoft.asc](https://packages.microsoft.com/keys/microsoft.asc) | gpg --dearmor > microsoft.gpg \
    && install -o root -g root -m 644 microsoft.gpg /etc/apt/trusted.gpg.d/ \
    && sh -c 'echo "deb [arch=amd64] [https://packages.microsoft.com/repos/edge](https://packages.microsoft.com/repos/edge) stable main" > /etc/apt/sources.list.d/microsoft-edge.list' \
    && rm microsoft.gpg \
    && apt-get update && apt-get install -y microsoft-edge-stable \
    && apt-get clean

# Настройка рабочей папки
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Прокидываем порт
EXPOSE 8000

# Команда запуска
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]