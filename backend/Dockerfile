# 1. Use Python 3.12 Slim (Explicit Version)
FROM python:3.12-slim

# 2. Install 'uv'
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 3. Set working directory
WORKDIR /app

# 4. Copy dependency files
COPY pyproject.toml uv.lock ./

# --- FIXED SECTION ---
# 5. Export dependencies to requirements.txt and install
# This is safer than 'uv sync' in Docker because it avoids venv/python-version magic
RUN uv export --frozen --no-dev --format requirements-txt > requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt
# ---------------------

# 6. Copy application code
COPY app ./app

# 7. Expose port
EXPOSE 80

# 8. Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
