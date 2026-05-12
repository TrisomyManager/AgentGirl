FROM python:3.11-slim

WORKDIR /app

# System deps for audio/image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source
COPY shared/ ./shared/
COPY core_orchestrator/ ./core_orchestrator/
COPY persona_engine/ ./persona_engine/
COPY memory_system/ ./memory_system/
COPY voice_layer/ ./voice_layer/
COPY action_layer/ ./action_layer/
COPY device_coordination/ ./device_coordination/
COPY gateway_adapter/ ./gateway_adapter/

# Default: can be overridden per service
CMD ["uvicorn", "core_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
