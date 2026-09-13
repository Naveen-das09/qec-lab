FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib QEC_DATA_DIR=/app/data
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home qec
COPY qec ./qec
COPY index.html app.js styles.css ./
RUN mkdir /app/data && chown -R qec:qec /app
USER qec
EXPOSE 4173
CMD ["uvicorn", "qec.server:app", "--host", "0.0.0.0", "--port", "4173"]
