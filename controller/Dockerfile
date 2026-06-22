FROM python:3.11-slim

WORKDIR /app

# Copy the entire controller directory
COPY . /app

# Install the application and its dependencies
RUN pip install --no-cache-dir .

# Default command (will be overridden by docker-compose for dev)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "42791"]
