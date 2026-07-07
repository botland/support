FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schemas ./schemas
COPY code_context ./code_context
COPY prompts ./prompts
COPY scripts ./scripts
COPY src ./src

ENV SUPPORT_PORT=8090
EXPOSE 8090

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${SUPPORT_PORT}"]