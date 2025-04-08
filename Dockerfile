# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables (using KEY=VALUE format)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if needed (e.g., for playwright)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*
# Add playwright install command if necessary
# RUN python -m playwright install --with-deps

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

# Command to run the application
CMD ["python", "src/notion_invoices/main.py"] 