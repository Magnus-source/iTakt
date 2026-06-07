FROM python:3.11-slim

WORKDIR /app

# Install build tools
RUN pip install --no-cache-dir setuptools>=68

# Copy package definition and install dependencies first (layer cache)
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Copy runtime files
COPY itakt.yaml .
COPY demo/ demo/

# Volume mount points
RUN mkdir -p traces

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "itakt"]
