FROM python:3.9-slim

# 1. Установка системных утилит и зависимостей для сборки
# Убираем ручное перечисление библиотек Chrome (libgconf и т.д.),
# так как apt-get install google-chrome-stable подтянет их сам.
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
    && rm -rf /var/lib/apt/lists/*

# 2. Установка Google Chrome
# Добавляем ключ и репозиторий Google, затем ставим браузер.
# apt сам найдет нужные библиотеки (libnss3, libglib и прочие) в репозитории Debian.
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 3. Настройка окружения
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Копируем код
COPY . .

# 5. Entrypoint
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]