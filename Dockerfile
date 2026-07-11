FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV LIBGL_ALWAYS_SOFTWARE=1

WORKDIR /app

COPY web/requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl xz-utils ca-certificates libgl1 libglib2.0-0 libxi6 libxxf86vm1 libxfixes3 \
    libsm6 libxext6 libxcursor1 libxrender1 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

ARG BLENDER_VERSION=4.2.0
RUN curl -fsSL "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" -o /tmp/blender.tar.xz \
 && tar -xf /tmp/blender.tar.xz -C /opt \
 && ln -sf "/opt/blender-${BLENDER_VERSION}-linux-x64/blender" /usr/local/bin/blender \
 && rm -f /tmp/blender.tar.xz

COPY . .

WORKDIR /app/web
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
