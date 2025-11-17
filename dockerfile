# Dockerfile (Corrected Python Path)

# Stage 1: Builder
FROM python:3.11-bookworm AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential cmake pkg-config libssl-dev libpq-dev \
        libboost-dev libboost-filesystem-dev libboost-system-dev libboost-regex-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# --- FIX 1: Set WORKDIR to /code ---
WORKDIR /code
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---
# Stage 2: Runtime
FROM python:3.11-slim-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# --- FIX 2: Set WORKDIR to /code ---
WORKDIR /code

# --- FIX 3: Set PYTHONPATH to /code ---
# This tells Python to look for modules in the /code directory
ENV PYTHONPATH /code

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/lib /usr/local/lib

# --- FIX 4: Copy your local 'app' folder TO /code/app ---
# This creates the correct package structure: /code/app/main.py
COPY ./app /code/app

# Copy environment files to the WORKDIR
COPY .env .
COPY .env.example .

EXPOSE 8080

# --- NO CHANGE NEEDED HERE ---
# This command now works because Python looks in /code (PYTHONPATH)
# finds the 'app' module, and then finds 'main.py' inside it.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]