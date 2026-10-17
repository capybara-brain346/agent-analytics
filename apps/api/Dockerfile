# One image for api, worker and migrate (on-prem.md: worker = api image, other command).
FROM python:3.15-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY src ./src

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system --uid 10001 app
USER 10001

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
