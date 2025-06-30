# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables (using KEY=VALUE format)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy only the dependency definition files first to leverage Docker cache
COPY pyproject.toml uv.lock ./

# Install project dependencies using uv
# uv pip sync respects the lockfile if present
# Using --system to install into the global site-packages
RUN uv pip sync --system pyproject.toml

# Copy the rest of the application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application
CMD ["python", "-m", "app.main"] 