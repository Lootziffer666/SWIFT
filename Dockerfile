FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY web/requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

RUN apt-get update \
 && apt-get install -y --no-install-recommends blender \
 && rm -rf /var/lib/apt/lists/* || true

COPY . .

WORKDIR /app/web
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
