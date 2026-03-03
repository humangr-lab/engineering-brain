FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application
COPY server/ server/
COPY client/ client/

# Expose port
EXPOSE 8420

# Run server
CMD ["python", "-m", "server.main", "--host", "0.0.0.0", "--port", "8420"]
