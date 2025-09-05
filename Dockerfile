FROM python:3.11.11-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

COPY . /app/

# Install dependencies using uv
RUN uv pip install --no-cache --system -e .

CMD ["python", "-m", "cfupdater.cfupdater"]