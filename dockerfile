# Stage 1: Builder - Installs build tools and Python dependencies
FROM python:3.11-bookworm AS builder
# Using the full 'bookworm' tag, not 'slim', to include more build tools

# Install essential build tools + libraries for pyarrow, psycopg2, etc.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        pkg-config \
        libssl-dev \
        libpq-dev \
        # Additional libraries often needed for pyarrow compilation
        libboost-dev \
        libboost-filesystem-dev \
        libboost-system-dev \
        libboost-regex-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip

WORKDIR /app
COPY requirements.txt .

# Install Python packages
# No --no-cache-dir here to allow caching between build steps if possible
RUN pip install -r requirements.txt

# ---

# Stage 2: Runtime - Final image with only necessary components
FROM python:3.11-slim-bookworm
# Switch back to slim for the final image

# Install runtime libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# Copy necessary compiled libraries (like pyarrow's .so files) if they aren't in site-packages
# This path might vary, adjust if needed after inspecting the builder stage
COPY --from=builder /usr/local/lib /usr/local/lib

# Copy application files and config
COPY ./app /app/app
# REMOVE the line 'COPY ./static /app/static' as it assumes the static folder is at the root.
# REMOVE the ambiguous line: COPY . /app/static 

# FIX: Copy the templates folder specifically to the correct path
# NOTE: Templates folder is inside the app directory in your local structure
COPY ./app/templates /app/app/templates 

# Copy environment files
COPY .env /app/.env  
COPY .env.example /app/.env.example

# Expose the application port
EXPOSE 8080

# The CMD to run the application using Python module execution
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]