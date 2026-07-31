FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Build gates (auditoría 2026-07-28): el linter prohíbe llamar tools
# decoradas (FunctionTool no es invocable desde fastmcp 2.7) y el smoke
# estático verifica que los 14 servidores importan y registran sus tools.
# Si cualquiera falla, la imagen no se construye.
RUN python scripts/lint_tool_calls.py . \
    && python scripts/smoke_tools.py --static

# Expose MCP gateway port
EXPOSE 8050

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8050/health')" || exit 1

CMD ["python", "main.py"]
