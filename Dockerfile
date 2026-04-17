FROM python:3.12-slim

LABEL org.opencontainers.image.title="ThinkNEO MCP Server"
LABEL org.opencontainers.image.description="Enterprise AI Control Plane — MCP remote server"
LABEL org.opencontainers.image.url="https://thinkneo.ai"
LABEL org.opencontainers.image.source="https://github.com/thinkneo-ai/mcp-server"
LABEL org.opencontainers.image.version="1.0.2"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --no-create-home appuser

WORKDIR /app

# Install dependencies first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source and metadata
COPY --chown=appuser:appgroup src/ src/
COPY --chown=appuser:appgroup templates/ templates/
COPY --chown=appuser:appgroup server.json glama.json LICENSE README.md ./

# Drop privileges
USER appuser

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "\
import urllib.request; \
req = urllib.request.Request('http://127.0.0.1:8081/mcp', \
    data=b'{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"id\":1,\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"healthcheck\",\"version\":\"1.0\"}}}', \
    headers={'Content-Type': 'application/json'}, method='POST'); \
urllib.request.urlopen(req, timeout=4)" \
    || exit 1

CMD ["python3", "-m", "uvicorn", "src.server:app", \
     "--host", "0.0.0.0", "--port", "8081", \
     "--workers", "2", \
     "--no-server-header", "--no-date-header", \
     "--timeout-keep-alive", "30"]
