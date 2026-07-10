from prometheus_client import Counter, Histogram

phi_records_processed_total = Counter(
    "phi_records_processed_total",
    "Total records that completed de-identification",
)

phi_entities_detected_total = Counter(
    "phi_entities_detected_total",
    "Total PHI entities detected across all records",
)

phi_claude_fallback_total = Counter(
    "phi_claude_fallback_total",
    "Records that triggered the Claude tier-2 fallback",
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=["method", "path", "status"],
)
