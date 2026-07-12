FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schemas ./schemas
COPY code_context ./code_context
COPY knowledge ./knowledge
COPY prompts ./prompts
COPY scripts ./scripts
COPY src ./src

RUN chmod +x /app/scripts/*.sh || true

# Grok CLI is expected via mounted host install (~/.grok/bin on PATH).
# Auth/credentials: mount host ~/.grok → /root/.grok (see compose.yml).
ENV HOME=/root
ENV PATH="/root/.grok/bin:${PATH}"
ENV SUPPORT_PORT=8090
# Default production CLI wiring (override freely to switch tools).
ENV AI_CLI_ADAPTER=stub
ENV AI_CLI_USE_PROMPT_FILE=true
ENV AI_CLI_CWD=code_root
ENV AI_CLI_PRIMARY_ROOT=backend
ENV AI_CLI_COMMAND="/app/scripts/ai_diagnose_grok.sh"
# Product guide (public L1) defaults — cli uses mounted Grok (~/.grok)
ENV GUIDE_AI_ADAPTER=cli
ENV GUIDE_AI_CLI_COMMAND="/app/scripts/ai_guide_grok.sh"
ENV GUIDE_AI_CLI_USE_PROMPT_FILE=true
ENV GUIDE_AI_CLI_TIMEOUT_SEC=180
ENV GUIDE_KNOWLEDGE_ROOT=/app/knowledge/product-guide
ENV GUIDE_PROMPT_PATH=/app/prompts/product-guide.txt

EXPOSE 8090

CMD ["/app/scripts/docker-entrypoint.sh"]
