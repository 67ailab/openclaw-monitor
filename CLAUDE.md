# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenClaw Monitoring is a metrics collection system for the OpenClaw CLI tool. It provides real-time visibility into OpenClaw usage (sessions, token consumption) alongside system metrics (CPU, memory, disk) using Prometheus, Grafana, and a custom Python exporter.

## Architecture

**Hybrid architecture with two components:**

1. **Dockerized monitoring stack** (docker-compose.yml): Prometheus (port 9090), Grafana (port 3000), Node Exporter (port 9100) running in an isolated `openclaw-net` bridge network.

2. **Host-based exporter** (exporter.py): Lightweight Python HTTP server on port 8000 that runs `openclaw sessions --json` and exposes Prometheus-compatible metrics. This MUST run on the host, not in Docker, because it needs access to the `openclaw` CLI.

Prometheus reaches the host exporter via `host.docker.internal:8000`.

## Commands

**Start monitoring stack:**
```bash
docker compose up -d
```

**Start the exporter (required, runs on host):**
```bash
python3 /home/james/monitoring-repo/exporter.py &
```

**Stop monitoring stack:**
```bash
docker compose down
```

**View service logs:**
```bash
docker compose logs -f prometheus
docker compose logs -f grafana
```

## Access Points

- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090
- Metrics endpoint: http://localhost:8000/metrics

## Key Files

- `exporter.py` - Custom Python metrics exporter with health check endpoint (no external dependencies)
- `docker-compose.yml` - Service definitions with health checks, pinned versions, and volume persistence
- `prometheus/prometheus.yml` - Scrape configuration (15s interval, 10s timeout, three targets)
- `grafana/provisioning/` - Auto-provisioned datasource and dashboard

## Metrics Exposed

**Session counts:** `openclaw_sessions_total`, `openclaw_sessions_active_1h`

**Per-session (labeled by session and model):**
- `openclaw_session_tokens_input`, `openclaw_session_tokens_output`
- `openclaw_session_tokens_cache_read`, `openclaw_session_tokens_cache_write`
- `openclaw_session_cost_usd`

**Aggregate totals:**
- `openclaw_tokens_input_total`, `openclaw_tokens_output_total`, `openclaw_tokens_total`
- `openclaw_tokens_cache_read_total`, `openclaw_tokens_cache_write_total`
- `openclaw_cost_total_usd`, `openclaw_cost_input_usd`, `openclaw_cost_output_usd`
- `openclaw_cost_cache_read_usd`, `openclaw_cost_cache_write_usd`

**Per-model aggregates (labeled by model):**
- `openclaw_model_tokens_input`, `openclaw_model_tokens_output`
- `openclaw_model_tokens_cache_read`, `openclaw_model_tokens_cache_write`
- `openclaw_model_cost_usd`

**System (from node-exporter):** `node_load*`, `node_memory_*`, `node_disk_*`

## Troubleshooting

If Prometheus shows "connection refused" for the openclaw target, the host exporter isn't running. Start it with `python3 /home/james/monitoring-repo/exporter.py &`.
