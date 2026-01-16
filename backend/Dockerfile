FROM python:3.9-slim

# 1. Установка системных зависимостей и Google Chrome
# Мы ставим wget, gnupg и библиотеки, нужные Хрому для рендера (даже в headless)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    fontconfig \
    fonts-dejavu \
    libpq-dev \
    gcc \
    netcat-openbsd \
    # Библиотеки для Chrome
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Настройка окружения
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Копируем код
COPY . .

# 4. Entrypoint (как у вас было)
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]