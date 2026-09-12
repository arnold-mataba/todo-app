# syntax=docker/dockerfile:1

FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
RUN addgroup --system app && adduser --system --ingroup app --home /app app
COPY --from=build /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=app:app . .
USER app
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health/', timeout=3).read()" || exit 1
CMD ["gunicorn", "todoproject.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "3"]
