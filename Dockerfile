FROM ghcr.io/astral-sh/uv:trixie-slim

# Add metadata
LABEL maintainer="Rémi Dubois"
LABEL description="Streamlit Playground"
LABEL org.opencontainers.image.source="https://github.com/remdub/streamlit-playground"

# Create non-root user
RUN groupadd --gid 1000 streamlit && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash streamlit

# Set working directory
WORKDIR /app
RUN chown streamlit:streamlit /app

# Switch to non-root user
USER streamlit

# Install dependencies first
COPY --chown=streamlit:streamlit .python-version pyproject.toml uv.lock ./
RUN uv sync --prerelease=allow --frozen --no-cache

# Copy application code
COPY --chown=streamlit:streamlit src/ ./src/
COPY --chown=streamlit:streamlit .streamlit/config.toml ./.streamlit/config.toml

# Configure the application
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD uv run python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# Start the application
CMD ["uv", "run", "streamlit", "run", "src/main.py", "--server.port=8501", "--server.address=0.0.0.0"]