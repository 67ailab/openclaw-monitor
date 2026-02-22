# Gemini Context: OpenClaw Monitoring Stack

This project provides a complete monitoring solution for the OpenClaw CLI tool, visualizing usage metrics like session counts and token usage. It combines standard monitoring tools (Prometheus, Grafana) with a custom Python-based exporter.

## Architecture

The system consists of two main parts:

1.  **Dockerized Monitoring Stack:**
    *   **Prometheus:** Collects and stores metrics. Configured to scrape the host machine for custom OpenClaw metrics.
    *   **Grafana:** Visualizes the data. Pre-configured dashboard available in `dashboard.json`.
    *   **Node Exporter:** Collects system-level metrics (CPU, RAM, etc.) from within the Docker network.

2.  **Host-based Exporter (`exporter.py`):**
    *   A lightweight Python HTTP server that runs directly on the host machine.
    *   Executes `openclaw sessions --json` to fetch real-time data from the CLI.
    *   Parses the JSON output and exposes Prometheus-compatible metrics on port `8000`.

## Key Files

*   **`exporter.py`**: The custom metrics exporter. **Crucial:** Must be running on the host for OpenClaw metrics to appear.
*   **`docker-compose.yml`**: Defines the Prometheus, Grafana, and Node Exporter services.
*   **`prometheus/prometheus.yml`**: Prometheus configuration. Note the `openclaw` job targeting `host.docker.internal:8000`.
*   **`dashboard.json`**: A JSON export of the Grafana dashboard, ready for import.

## Setup & Usage

### 1. Prerequisites
*   Docker & Docker Compose installed.
*   `openclaw` CLI tool installed and accessible in the system PATH.
*   Python 3 installed.

### 2. Start the Monitoring Stack
Launch the containerized services:
```bash
docker-compose up -d
```

### 3. Start the Custom Exporter
Run the Python script on the host machine to start exposing metrics:
```bash
python3 exporter.py
```
*   The exporter runs on `http://localhost:8000`.
*   Metrics are available at `http://localhost:8000/metrics`.

### 4. Access Dashboards
*   **Grafana:** [http://localhost:3000](http://localhost:3000) (Default login: `admin` / `admin`).
*   **Prometheus:** [http://localhost:9090](http://localhost:9090).

## Custom Metrics

The `exporter.py` script exposes the following metrics:

### Global Metrics (Unlabeled)
| Metric Name | Description |
| :--- | :--- |
| `openclaw_sessions_total` | Total number of recorded sessions. |
| `openclaw_sessions_active_1h` | Number of sessions updated in the last hour. |

### Per-Session Metrics (Labeled)
These metrics include `session` and `model` labels for granular breakdown.
| Metric Name | Description |
| :--- | :--- |
| `openclaw_tokens_input_total` | Input tokens for the specific session. |
| `openclaw_tokens_output_total` | Output tokens for the specific session. |

## Development Notes

*   **Aggregation:** Use `sum(openclaw_tokens_input_total)` for global totals or `sum by (model) (openclaw_tokens_input_total)` to see usage per model.
*   **Session ID:** The `session` label is pulled from the `key` (or `sessionId`) in the OpenClaw output.
