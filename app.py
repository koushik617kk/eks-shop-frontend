"""
shop-frontend: Entrypoint for the 3-tier demo application.
Serves the UI, calls order-service and file-service backends.
Logs every request as structured JSON to stdout (for Prometheus/CloudWatch).
"""
import logging
import json
import os
import time
import requests
from flask import Flask, jsonify, request, Response
import prometheus_client
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# ──────────────────────────────────────────────
# tructured JSON Logger
# ──────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": "shop-frontend",
            "message": record.getMessage(),
        }
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("shop-frontend")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ──────────────────────────────────────────────
# Prometheus Metrics
# ──────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "frontend_http_requests_total",
    "Total HTTP requests to shop-frontend",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "frontend_http_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"]
)

# ──────────────────────────────────────────────
# Backends (Kubernetes DNS names)
# ──────────────────────────────────────────────
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:5000")
FILE_SERVICE_URL  = os.getenv("FILE_SERVICE_URL",  "http://file-service:5000")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "shop-frontend"}), 200


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/")
def index():
    start = time.time()
    REQUEST_COUNT.labels("GET", "/", "200").inc()
    REQUEST_LATENCY.labels("/").observe(time.time() - start)
    logger.info("GET / — serving home page")
    return jsonify({
        "service": "shop-frontend",
        "message": "Welcome to the EKS Demo Shop!",
        "version": os.getenv("APP_VERSION", "v1.0.0"),
    })


@app.route("/place-order", methods=["POST"])
def place_order():
    """Calls order-service to process an order."""
    start = time.time()
    payload = request.get_json(silent=True) or {"item": "default-item"}
    
    try:
        resp = requests.post(f"{ORDER_SERVICE_URL}/process", json=payload, timeout=5)
        result = resp.json()
        status = str(resp.status_code)
    except Exception as e:
        logger.error(f"Failed to reach order-service: {e}")
        result = {"error": str(e)}
        status = "503"

    duration = time.time() - start
    REQUEST_COUNT.labels("POST", "/place-order", status).inc()
    REQUEST_LATENCY.labels("/place-order").observe(duration)
    logger.info(f"POST /place-order — order-service responded in {duration:.3f}s")
    return jsonify(result), int(status)


@app.route("/upload-file", methods=["POST"])
def upload_file():
    """Calls file-service to create a file on the PVC."""
    start = time.time()
    payload = request.get_json(silent=True) or {"filename": "test-file.txt"}

    try:
        resp = requests.post(f"{FILE_SERVICE_URL}/create", json=payload, timeout=5)
        result = resp.json()
        status = str(resp.status_code)
    except Exception as e:
        logger.error(f"Failed to reach file-service: {e}")
        result = {"error": str(e)}
        status = "503"

    duration = time.time() - start
    REQUEST_COUNT.labels("POST", "/upload-file", status).inc()
    REQUEST_LATENCY.labels("/upload-file").observe(duration)
    logger.info(f"POST /upload-file — file-service responded in {duration:.3f}s")
    return jsonify(result), int(status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
