# ---------------------------------------------------------------------------
# Autonomous Data Governance Assistant
# CPU-only image. Boots `python run.py` on port 8000.
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project.
COPY . .

# Ensure runtime directories exist.
RUN mkdir -p logs app/outputs app/database

EXPOSE 8000

# entrypoint.sh just execs `python run.py`; kept as a layer of indirection
# so organizers can override behaviour without rebuilding the image.
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
