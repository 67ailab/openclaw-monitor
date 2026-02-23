import subprocess
import json
import os
import signal
import sys
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer

SUBPROCESS_TIMEOUT = 10
CACHE_TTL = int(os.environ.get('OPENCLAW_CACHE_TTL', '10'))
EXPORTER_VERSION = '1.0.0'

_cache = {'data': None, 'timestamp': 0}
_shutdown = False


def log_error(message):
    print(f"[ERROR] {message}", file=sys.stderr)


def escape_label(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def get_nested(d, *keys, default=0):
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    val = d if d is not None else default
    return val if isinstance(val, (int, float)) else default


def check_openclaw_available():
    try:
        result = subprocess.run(
            ['openclaw', '--version'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def fetch_metrics():
    now = time.time()
    if _cache['data'] is not None and (now - _cache['timestamp']) < CACHE_TTL:
        return _cache['data']

    try:
        result = subprocess.run(
            ['openclaw', 'sessions', '--json'],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or f'exit code {result.returncode}'
            log_error(f"openclaw command failed: {error_msg}")
            return None

        data = json.loads(result.stdout)
        _cache['data'] = data
        _cache['timestamp'] = now
        return data
    except subprocess.TimeoutExpired:
        log_error(f"openclaw command timed out after {SUBPROCESS_TIMEOUT}s")
        return None
    except json.JSONDecodeError as e:
        log_error(f"JSON parse error: {e}")
        return None
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        return None


def build_metrics(data):
    if data is None:
        return '# Error: Unable to fetch session data\n'

    sessions = data.get('sessions', [])
    now = time.time() * 1000

    count = len(sessions)
    active_1h = sum(1 for s in sessions if (now - s.get('updatedAt', 0)) < 3600000)

    totals = {
        'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0,
        'cost': 0.0, 'input_cost': 0.0, 'output_cost': 0.0,
        'cache_read_cost': 0.0, 'cache_write_cost': 0.0
    }

    model_totals = defaultdict(lambda: {
        'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0, 'cost': 0.0
    })

    metrics = [
        '# HELP openclaw_exporter_version Exporter version',
        '# TYPE openclaw_exporter_version gauge',
        f'openclaw_exporter_version{{version="{EXPORTER_VERSION}"}} 1',
        '# HELP openclaw_sessions_total Total number of OpenClaw sessions',
        '# TYPE openclaw_sessions_total gauge',
        f'openclaw_sessions_total {count}',
        '# HELP openclaw_sessions_active_1h Sessions updated in the last hour',
        '# TYPE openclaw_sessions_active_1h gauge',
        f'openclaw_sessions_active_1h {active_1h}',
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

    for s in sessions:
        s_id = escape_label(s.get('key') or s.get('sessionId') or 'unknown')
        model = escape_label(s.get('model') or 'unknown')
        labels = f'session="{s_id}",model="{model}"'

        in_tok = int(get_nested(s, 'inputTokens'))
        out_tok = int(get_nested(s, 'outputTokens'))
        cache_read = int(get_nested(s, 'cacheReadTokens'))
        cache_write = int(get_nested(s, 'cacheWriteTokens'))

        usage = s.get('usage', {}) if isinstance(s.get('usage'), dict) else {}
        session_cost = float(get_nested(usage, 'totalCost') or get_nested(s, 'cost'))

        totals['input'] += in_tok
        totals['output'] += out_tok
        totals['cache_read'] += cache_read
        totals['cache_write'] += cache_write
        totals['cost'] += session_cost
        totals['input_cost'] += get_nested(usage, 'inputCost')
        totals['output_cost'] += get_nested(usage, 'outputCost')
        totals['cache_read_cost'] += get_nested(usage, 'cacheReadCost')
        totals['cache_write_cost'] += get_nested(usage, 'cacheWriteCost')

        model_totals[model]['input'] += in_tok
        model_totals[model]['output'] += out_tok
        model_totals[model]['cache_read'] += cache_read
        model_totals[model]['cache_write'] += cache_write
        model_totals[model]['cost'] += session_cost

        metrics.extend([
            f'openclaw_session_tokens_input{{{labels}}} {in_tok}',
            f'openclaw_session_tokens_output{{{labels}}} {out_tok}',
            f'openclaw_session_tokens_cache_read{{{labels}}} {cache_read}',
            f'openclaw_session_tokens_cache_write{{{labels}}} {cache_write}',
            f'openclaw_session_cost_usd{{{labels}}} {session_cost}',
        ])

    total_tokens = totals['input'] + totals['output'] + totals['cache_read'] + totals['cache_write']
    metrics.extend([
        '# HELP openclaw_tokens_input_total Total input tokens across all sessions',
        '# TYPE openclaw_tokens_input_total gauge',
        f'openclaw_tokens_input_total {totals["input"]}',
        '# HELP openclaw_tokens_output_total Total output tokens across all sessions',
        '# TYPE openclaw_tokens_output_total gauge',
        f'openclaw_tokens_output_total {totals["output"]}',
        '# HELP openclaw_tokens_cache_read_total Total cache read tokens across all sessions',
        '# TYPE openclaw_tokens_cache_read_total gauge',
        f'openclaw_tokens_cache_read_total {totals["cache_read"]}',
        '# HELP openclaw_tokens_cache_write_total Total cache write tokens across all sessions',
        '# TYPE openclaw_tokens_cache_write_total gauge',
        f'openclaw_tokens_cache_write_total {totals["cache_write"]}',
        '# HELP openclaw_tokens_total Total tokens across all sessions',
        '# TYPE openclaw_tokens_total gauge',
        f'openclaw_tokens_total {total_tokens}',
        '# HELP openclaw_cost_total_usd Total cost in USD across all sessions',
        '# TYPE openclaw_cost_total_usd gauge',
        f'openclaw_cost_total_usd {totals["cost"]}',
        '# HELP openclaw_cost_input_usd Total input cost in USD',
        '# TYPE openclaw_cost_input_usd gauge',
        f'openclaw_cost_input_usd {totals["input_cost"]}',
        '# HELP openclaw_cost_output_usd Total output cost in USD',
        '# TYPE openclaw_cost_output_usd gauge',
        f'openclaw_cost_output_usd {totals["output_cost"]}',
        '# HELP openclaw_cost_cache_read_usd Total cache read cost in USD',
        '# TYPE openclaw_cost_cache_read_usd gauge',
        f'openclaw_cost_cache_read_usd {totals["cache_read_cost"]}',
        '# HELP openclaw_cost_cache_write_usd Total cache write cost in USD',
        '# TYPE openclaw_cost_cache_write_usd gauge',
        f'openclaw_cost_cache_write_usd {totals["cache_write_cost"]}',
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
    ])

    for model, mt in model_totals.items():
        label = f'model="{model}"'
        metrics.extend([
            f'openclaw_model_tokens_input{{{label}}} {mt["input"]}',
            f'openclaw_model_tokens_output{{{label}}} {mt["output"]}',
            f'openclaw_model_tokens_cache_read{{{label}}} {mt["cache_read"]}',
            f'openclaw_model_tokens_cache_write{{{label}}} {mt["cache_write"]}',
            f'openclaw_model_cost_usd{{{label}}} {mt["cost"]}',
        ])

    return '\n'.join(metrics) + '\n'


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()
            data = fetch_metrics()
            self.wfile.write(build_metrics(data).encode('utf-8'))
        elif self.path == '/ready':
            self.send_response(200 if check_openclaw_available() else 503)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK\n' if check_openclaw_available() else b'Not Ready\n')
        elif self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK\n')
        else:
            self.send_response(404)
            self.end_headers()


def signal_handler(signum, frame):
    global _shutdown
    _shutdown = True
    print("\nShutting down gracefully...", file=sys.stderr)
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    server = HTTPServer(('0.0.0.0', 8000), MetricsHandler)
    print(f"OpenClaw Exporter v{EXPORTER_VERSION} started on port 8000 (cache TTL: {CACHE_TTL}s)")
    server.serve_forever()
