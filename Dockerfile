FROM python:3.11.11-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml /app/

# Install dependencies using uv
RUN uv pip install --no-cache --system -e .

# Copy the script
COPY cfupdater.py /app/

ENV OP_SERVICE_ACCOUNT_TOKENENV=""
CMD ["python", "cloudflare_dns_updater.py"]
