FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN addgroup --system jarvis && adduser --system --ingroup jarvis --home /app jarvis
WORKDIR /app
COPY pyproject.toml constraints.txt README.md LICENSE ./
COPY jarvis_home ./jarvis_home
RUN pip install --upgrade pip && pip install -c constraints.txt .
RUN mkdir -p /app/data /app/backups /app/plugins && chown -R jarvis:jarvis /app
USER jarvis
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3)" || exit 1
CMD ["uvicorn", "jarvis_home.main:app", "--host", "0.0.0.0", "--port", "8787", "--proxy-headers"]
