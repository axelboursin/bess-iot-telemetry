# One image, two entrypoints: bess-sim (simulator) and bess-agent (edge agent).
# Built for linux/amd64 and linux/arm64, since edge gateways are often ARM.

FROM ghcr.io/astral-sh/uv:0.5.11 AS uv

FROM python:3.15-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.15-slim AS runtime
RUN groupadd --system bess && useradd --system --gid bess --no-create-home bess
COPY --from=build --chown=root:root /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER bess
EXPOSE 5020
ENTRYPOINT ["bess-agent"]
