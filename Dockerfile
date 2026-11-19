FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/srv/data/model-cache
WORKDIR /srv
RUN useradd --create-home --uid 10001 policy && mkdir -p /srv/data/runtime /srv/data/model-cache && chown -R policy:policy /srv
COPY --chown=policy:policy . /srv
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir '.[ml]'
USER policy
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1","--limit-concurrency","40","--no-access-log"]
