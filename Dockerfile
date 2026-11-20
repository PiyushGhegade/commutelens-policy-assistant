FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 ANONYMIZED_TELEMETRY=False
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN useradd --create-home commuter && mkdir -p /app/data && chown -R commuter:commuter /app
USER commuter
# Download once at build time, never during a measured question.
RUN python -c "from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2; ONNXMiniLM_L6_V2()(['warm up policy model'])"
COPY --chown=commuter:commuter app ./app
COPY --chown=commuter:commuter static ./static
COPY --chown=commuter:commuter policies ./policies
COPY --chown=commuter:commuter examples ./examples
COPY --chown=commuter:commuter evaluation ./evaluation
COPY --chown=commuter:commuter tests ./tests
COPY --chown=commuter:commuter scripts ./scripts
COPY pytest.ini ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
