FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home app
COPY shindan ./shindan
USER app
CMD ["python", "-m", "shindan.web"]
