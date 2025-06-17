# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables for better Python behavior in containers
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Install system dependencies and clean up in single layer to reduce image size
RUN apt-get update && apt-get install -y \
    gcc \
    libc6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies with optimizations
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Clean pip cache
    pip cache purge

# Copy bot code
COPY bot.py ./bot.py

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1000 botuser

# Create logs directory and set proper permissions
RUN mkdir -p /app/logs /app/tmp && \
    chown -R botuser:botuser /app && \
    chmod 755 /app/logs

# Switch to non-root user
USER botuser

# Create a simple health check script
RUN echo '#!/bin/bash\n\
python3 -c "\
import asyncio\n\
import aiohttp\n\
import sys\n\
\n\
async def check():\n\
    try:\n\
        connector = aiohttp.TCPConnector(limit=1)\n\
        session = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=5))\n\
        async with session.get(\"https://discord.com/api/v10/gateway\") as resp:\n\
            success = resp.status == 200\n\
        await session.close()\n\
        await connector.close()\n\
        sys.exit(0 if success else 1)\n\
    except Exception as e:\n\
        print(f\"Health check failed: {e}\")\n\
        sys.exit(1)\n\
\n\
asyncio.run(check())\n\
"' > /app/healthcheck.sh && chmod +x /app/healthcheck.sh

# Health check using the script
HEALTHCHECK --interval=60s --timeout=15s --start-period=120s --retries=3 \
    CMD /app/healthcheck.sh

# Set resource limits at runtime (these can be overridden by docker-compose)
ENV MALLOC_TRIM_THRESHOLD_=131072

# Run the bot with proper signal handling
CMD ["python", "-u", "bot.py"]