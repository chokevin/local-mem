# Multi-stage build for local-mem
FROM python:3.12-slim as builder

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv venv && uv pip install --system -e .

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY src/ ./src/
COPY pyproject.toml ./

# Create data directory for persistence
RUN mkdir -p /app/data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV MEM_PROFILE=prod
ENV MEM_DATA_DIR=/app/data

# Expose ports
# 8080 - Web UI
# 3000 - MCP server (if needed)
EXPOSE 8080 3000

# Default command runs the web UI
CMD ["python", "-m", "src.web", "--host", "0.0.0.0", "--port", "8080"]
