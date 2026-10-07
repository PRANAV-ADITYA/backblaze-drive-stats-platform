# The ingestion code, packed to run anywhere: fetch, extract and bookkeeping.
FROM python:3.11-slim

# uv, the same installer used on the Mac, copied from its official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install the exact package versions from uv.lock, without dev tools.
# This comes before the code so a code change doesn't reinstall the packages.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# The code and the contract it reads.
COPY fetcher/ fetcher/
COPY contracts/ contracts/

# Use the installed packages, and print output straight away so logs appear live.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

# Start as: python -m <module> <arguments>. The module is chosen at run time.
ENTRYPOINT ["python", "-m"]
CMD ["fetcher.fetch", "--help"]
