FROM python:3.9-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list \
    && apt-get update && apt-get install -y microsoft-edge-stable \
    && apt-get clean

# Автоматическая установка Edge Driver (соответствующего версии браузера)
RUN EDGE_VERSION=$(microsoft-edge --version | cut -d' ' -f3) && \
    wget -q "https://msedgedriver.azureedge.net/$EDGE_VERSION/edgedriver_linux64.zip" && \
    unzip edgedriver_linux64.zip && \
    mv msedgedriver /usr/local/bin/msedgedriver && \
    chmod +x /usr/local/bin/msedgedriver && \
    rm edgedriver_linux64.zip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]