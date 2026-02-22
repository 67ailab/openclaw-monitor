import subprocess
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

SUBPROCESS_TIMEOUT = 10  # seconds


def escape_label(value):
    """Escape a string for use as a Prometheus label value."""
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


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

                metrics = [
                    '# HELP openclaw_sessions_total Total number of OpenClaw sessions',
                    '# TYPE openclaw_sessions_total gauge',
                    f'openclaw_sessions_total {count}',
                    '# HELP openclaw_sessions_active_1h Sessions updated in the last hour',
                    '# TYPE openclaw_sessions_active_1h gauge',
                    f'openclaw_sessions_active_1h {active_1h}',
                    '# HELP openclaw_tokens_input_total Total input tokens per session',
                    '# TYPE openclaw_tokens_input_total counter',
                    '# HELP openclaw_tokens_output_total Total output tokens per session',
                    '# TYPE openclaw_tokens_output_total counter',
                ]

                # Per-session token metrics
                for s in sessions:
                    s_id = escape_label(s.get('key') or s.get('sessionId') or 'unknown')
                    model = escape_label(s.get('model') or 'unknown')
                    labels = f'session="{s_id}",model="{model}"'

                    in_tok = s.get('inputTokens', 0) or 0
                    out_tok = s.get('outputTokens', 0) or 0

                    metrics.append(f'openclaw_tokens_input_total{{{labels}}} {in_tok}')
                    metrics.append(f'openclaw_tokens_output_total{{{labels}}} {out_tok}')

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
