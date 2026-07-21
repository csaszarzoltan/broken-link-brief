FROM python:3.11-slim

WORKDIR /app

# Copy dependency files first for Docker layer caching
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# Expose default port (Railway overrides with PORT env var)
EXPOSE 8000

# Run the app
CMD ["python", "-m", "brokenlinkbrief.app"]
