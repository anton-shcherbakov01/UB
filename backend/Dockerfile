FROM python:3.9-slim

# 1. Установка системных утилит
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl fontconfig \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list \
    && apt-get update && apt-get install -y microsoft-edge-stable \
    && apt-get clean

# 2. Установка шрифта для PDF (DejaVuSans)
RUN wget -q https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2.37/dejavu-fonts-ttf-2.37.zip \
    && unzip dejavu-fonts-ttf-2.37.zip \
    && mkdir -p /usr/share/fonts/truetype/dejavu \
    && cp dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf /usr/share/fonts/truetype/dejavu/ \
    && fc-cache -f -v \
    && rm -rf dejavu-fonts-ttf-2.37.zip dejavu-fonts-ttf-2.37

# 3. Установка драйвера Edge
RUN EDGE_VERSION=$(microsoft-edge --version | grep -oE "[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+") && \
    echo "Browser Version: $EDGE_VERSION" && \
    curl -k -L -o edgedriver_linux64.zip "https://msedgedriver.azureedge.net/$EDGE_VERSION/edgedriver_linux64.zip" && \
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