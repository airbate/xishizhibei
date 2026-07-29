FROM node:22-alpine AS web-build
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY data ./data
COPY --from=web-build /web/dist ./frontend/dist

RUN pip install --no-cache-dir .

ENV APP_DATA_DIR=/app/storage
RUN mkdir -p /app/storage
EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
