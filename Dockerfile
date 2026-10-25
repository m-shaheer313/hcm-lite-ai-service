# Optional local container build. The hosted deploy on Render uses its
# native Python environment (pip install uv && uv sync), NOT this file.

FROM python:3.13-slim

WORKDIR /app

# uv for dependency management, then the locked project.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# Secrets come from env at runtime; nothing is baked into the image.
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
