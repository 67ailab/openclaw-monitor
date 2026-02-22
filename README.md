# OpenClaw Monitor

This repository contains the monitoring stack for OpenClaw, including Prometheus, Grafana, Node Exporter, and a custom OpenClaw metrics exporter.

## Components

- **Prometheus**: Metrics collection and storage.
- **Grafana**: Visualization dashboard.
- **Node Exporter**: System-level metrics (CPU, Memory, Disk).
- **OpenClaw Exporter**: Custom Python exporter that collects metrics from the OpenClaw CLI.

## Quick Start

### 1. Requirements

- Docker and Docker Compose
- OpenClaw CLI installed on the host

### 2. Running the stack

```bash
docker-compose up -d
```

### 3. Custom Exporter

The custom exporter (`exporter.py`) runs on the host to access the `openclaw` CLI. It can be started with:

```bash
python3 exporter.py
```

## Access

- **Grafana**: [http://localhost:3000](http://localhost:3000) (User: `admin` / Pass: `admin`)
- **Prometheus**: [http://localhost:9090](http://localhost:9090)
- **Metrics Endpoint**: [http://localhost:8000/metrics](http://localhost:8000/metrics)

## Troubleshooting

### Connection Refused (OpenClaw Metrics)
If Prometheus shows a `connection refused` error for the `openclaw` target, the custom exporter is likely not running on the host.

To start it:
```bash
python3 exporter.py &
```

## Configuration

- `prometheus/prometheus.yml`: Prometheus scrape configuration.
- `docker-compose.yml`: Container definitions.
- `dashboard.json`: Exported Grafana dashboard definition.
