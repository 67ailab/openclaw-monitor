import subprocess
import json
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer

SUBPROCESS_TIMEOUT = 10  # seconds


def escape_label(value):
    """Escape a string for use as a Prometheus label value."""
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def get_nested(d, *keys, default=0):
    """Safely get nested dictionary values."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d if d is not None else default


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass

    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()

            try:
                result = subprocess.run(
                    ['openclaw', 'sessions', '--json'],
                    capture_output=True,
                    text=True,
                    timeout=SUBPROCESS_TIMEOUT
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or f'exit code {result.returncode}'
                    self.wfile.write(f'# Error running openclaw: {error_msg}\n'.encode('utf-8'))
                    return

                data = json.loads(result.stdout)
                sessions = data.get('sessions', [])
                now = time.time() * 1000

                # Global metrics
                count = len(sessions)
                active_1h = sum(1 for s in sessions if (now - s.get('updatedAt', 0)) < 3600000)

                # Aggregate totals (similar to usage page UsageTotals)
                total_input = 0
                total_output = 0
                total_cache_read = 0
                total_cache_write = 0
                total_cost = 0.0
                input_cost = 0.0
                output_cost = 0.0
                cache_read_cost = 0.0
                cache_write_cost = 0.0

                # Per-model aggregates
                model_totals = defaultdict(lambda: {
                    'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0, 'cost': 0.0
                })

                metrics = [
                    '# HELP openclaw_sessions_total Total number of OpenClaw sessions',
                    '# TYPE openclaw_sessions_total gauge',
                    f'openclaw_sessions_total {count}',
                    '# HELP openclaw_sessions_active_1h Sessions updated in the last hour',
                    '# TYPE openclaw_sessions_active_1h gauge',
                    f'openclaw_sessions_active_1h {active_1h}',
                ]

                # Per-session metrics headers
                per_session_headers = [
                    '# HELP openclaw_session_tokens_input Input tokens for session',
                    '# TYPE openclaw_session_tokens_input gauge',
                    '# HELP openclaw_session_tokens_output Output tokens for session',
                    '# TYPE openclaw_session_tokens_output gauge',
                    '# HELP openclaw_session_tokens_cache_read Cache read tokens for session',
                    '# TYPE openclaw_session_tokens_cache_read gauge',
                    '# HELP openclaw_session_tokens_cache_write Cache write tokens for session',
                    '# TYPE openclaw_session_tokens_cache_write gauge',
                    '# HELP openclaw_session_cost_usd Session cost in USD',
                    '# TYPE openclaw_session_cost_usd gauge',
                ]
                metrics.extend(per_session_headers)

                per_session_metrics = []

                # Per-session token and cost metrics
                for s in sessions:
                    s_id = escape_label(s.get('key') or s.get('sessionId') or 'unknown')
                    model = escape_label(s.get('model') or 'unknown')
                    labels = f'session="{s_id}",model="{model}"'

                    # Token counts (usage page fields: input, output, cacheRead, cacheWrite)
                    in_tok = get_nested(s, 'inputTokens')
                    out_tok = get_nested(s, 'outputTokens')
                    cache_read = get_nested(s, 'cacheReadTokens')
                    cache_write = get_nested(s, 'cacheWriteTokens')

                    # Cost data (usage page has cost breakdown)
                    usage = s.get('usage', {}) if isinstance(s.get('usage'), dict) else {}
                    session_cost = get_nested(usage, 'totalCost')
                    session_input_cost = get_nested(usage, 'inputCost')
                    session_output_cost = get_nested(usage, 'outputCost')
                    session_cache_read_cost = get_nested(usage, 'cacheReadCost')
                    session_cache_write_cost = get_nested(usage, 'cacheWriteCost')

                    # If no usage.totalCost, try top-level cost field
                    if session_cost == 0:
                        session_cost = get_nested(s, 'cost')

                    # Accumulate totals
                    total_input += in_tok
                    total_output += out_tok
                    total_cache_read += cache_read
                    total_cache_write += cache_write
                    total_cost += session_cost
                    input_cost += session_input_cost
                    output_cost += session_output_cost
                    cache_read_cost += session_cache_read_cost
                    cache_write_cost += session_cache_write_cost

                    # Per-model aggregates
                    model_totals[model]['input'] += in_tok
                    model_totals[model]['output'] += out_tok
                    model_totals[model]['cache_read'] += cache_read
                    model_totals[model]['cache_write'] += cache_write
                    model_totals[model]['cost'] += session_cost

                    per_session_metrics.append(f'openclaw_session_tokens_input{{{labels}}} {in_tok}')
                    per_session_metrics.append(f'openclaw_session_tokens_output{{{labels}}} {out_tok}')
                    per_session_metrics.append(f'openclaw_session_tokens_cache_read{{{labels}}} {cache_read}')
                    per_session_metrics.append(f'openclaw_session_tokens_cache_write{{{labels}}} {cache_write}')
                    per_session_metrics.append(f'openclaw_session_cost_usd{{{labels}}} {session_cost}')

                metrics.extend(per_session_metrics)

                # Aggregate totals (similar to usage page totals display)
                total_tokens = total_input + total_output + total_cache_read + total_cache_write
                aggregate_metrics = [
                    '# HELP openclaw_tokens_input_total Total input tokens across all sessions',
                    '# TYPE openclaw_tokens_input_total gauge',
                    f'openclaw_tokens_input_total {total_input}',
                    '# HELP openclaw_tokens_output_total Total output tokens across all sessions',
                    '# TYPE openclaw_tokens_output_total gauge',
                    f'openclaw_tokens_output_total {total_output}',
                    '# HELP openclaw_tokens_cache_read_total Total cache read tokens across all sessions',
                    '# TYPE openclaw_tokens_cache_read_total gauge',
                    f'openclaw_tokens_cache_read_total {total_cache_read}',
                    '# HELP openclaw_tokens_cache_write_total Total cache write tokens across all sessions',
                    '# TYPE openclaw_tokens_cache_write_total gauge',
                    f'openclaw_tokens_cache_write_total {total_cache_write}',
                    '# HELP openclaw_tokens_total Total tokens across all sessions',
                    '# TYPE openclaw_tokens_total gauge',
                    f'openclaw_tokens_total {total_tokens}',
                    '# HELP openclaw_cost_total_usd Total cost in USD across all sessions',
                    '# TYPE openclaw_cost_total_usd gauge',
                    f'openclaw_cost_total_usd {total_cost}',
                    '# HELP openclaw_cost_input_usd Total input cost in USD',
                    '# TYPE openclaw_cost_input_usd gauge',
                    f'openclaw_cost_input_usd {input_cost}',
                    '# HELP openclaw_cost_output_usd Total output cost in USD',
                    '# TYPE openclaw_cost_output_usd gauge',
                    f'openclaw_cost_output_usd {output_cost}',
                    '# HELP openclaw_cost_cache_read_usd Total cache read cost in USD',
                    '# TYPE openclaw_cost_cache_read_usd gauge',
                    f'openclaw_cost_cache_read_usd {cache_read_cost}',
                    '# HELP openclaw_cost_cache_write_usd Total cache write cost in USD',
                    '# TYPE openclaw_cost_cache_write_usd gauge',
                    f'openclaw_cost_cache_write_usd {cache_write_cost}',
                ]
                metrics.extend(aggregate_metrics)

                # Per-model aggregate metrics
                model_metrics = [
                    '# HELP openclaw_model_tokens_input Total input tokens by model',
                    '# TYPE openclaw_model_tokens_input gauge',
                    '# HELP openclaw_model_tokens_output Total output tokens by model',
                    '# TYPE openclaw_model_tokens_output gauge',
                    '# HELP openclaw_model_tokens_cache_read Total cache read tokens by model',
                    '# TYPE openclaw_model_tokens_cache_read gauge',
                    '# HELP openclaw_model_tokens_cache_write Total cache write tokens by model',
                    '# TYPE openclaw_model_tokens_cache_write gauge',
                    '# HELP openclaw_model_cost_usd Total cost by model in USD',
                    '# TYPE openclaw_model_cost_usd gauge',
                ]
                for model, totals in model_totals.items():
                    label = f'model="{model}"'
                    model_metrics.append(f'openclaw_model_tokens_input{{{label}}} {totals["input"]}')
                    model_metrics.append(f'openclaw_model_tokens_output{{{label}}} {totals["output"]}')
                    model_metrics.append(f'openclaw_model_tokens_cache_read{{{label}}} {totals["cache_read"]}')
                    model_metrics.append(f'openclaw_model_tokens_cache_write{{{label}}} {totals["cache_write"]}')
                    model_metrics.append(f'openclaw_model_cost_usd{{{label}}} {totals["cost"]}')
                metrics.extend(model_metrics)

                self.wfile.write('\n'.join(metrics).encode('utf-8') + b'\n')

            except subprocess.TimeoutExpired:
                self.wfile.write(f'# Error: openclaw command timed out after {SUBPROCESS_TIMEOUT}s\n'.encode('utf-8'))
            except json.JSONDecodeError as e:
                self.wfile.write(f'# Error parsing JSON: {e}\n'.encode('utf-8'))
            except Exception as e:
                self.wfile.write(f'# Error: {e}\n'.encode('utf-8'))

        elif self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK\n')
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8000), MetricsHandler)
    print("OpenClaw Exporter started on port 8000")
    server.serve_forever()
