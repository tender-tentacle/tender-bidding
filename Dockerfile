# --- UI Builder Stage ---
FROM node:20-slim AS ui-builder
WORKDIR /app/ui
COPY ui/package*.json ./
RUN npm install --legacy-peer-deps
COPY ui/ ./
RUN npm run build -- --base=/ms/bidding/

# --- Python Backend Stage ---
FROM python:3.13-slim-bookworm

WORKDIR /app

# System deps for MSSQL (isolated Azure SQL server in prod)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg2 ca-certificates unixodbc-dev g++ \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=ui-builder /app/ui/dist ./ui/dist

ENV PYTHONPATH="/app"

# Non-root; /data holds the local SQLite fallback DB when DATABASE_URL is unset.
RUN useradd -m appuser && chown -R appuser:appuser /app \
    && mkdir -p /data && chown appuser:appuser /data
USER appuser

EXPOSE 8014

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8014"]
