FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENTCAD_DATABASE_PATH=/data/agentcad.db \
    AGENTCAD_FRONTEND_DIST=/app/frontend/dist
RUN apt-get update \
    && apt-get install -y --no-install-recommends libcairo2 libpango-1.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir .
VOLUME ["/data"]
EXPOSE 8000
CMD ["agentcad", "serve", "--host", "0.0.0.0", "--port", "8000"]
