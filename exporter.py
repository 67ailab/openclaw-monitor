import subprocess
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()
            
            try:
                # Run openclaw sessions
                result = subprocess.run(['openclaw', 'sessions', '--json'], capture_output=True, text=True)
                data = json.loads(result.stdout)
                
                sessions = data.get('sessions', [])
                now = time.time() * 1000
                
                # Global metrics (unlabeled)
                count = len(sessions)
                active_1h = sum(1 for s in sessions if (now - s.get('updatedAt', 0)) < 3600000)
                
                metrics = [
                    f'openclaw_sessions_total {count}',
                    f'openclaw_sessions_active_1h {active_1h}'
                ]
                
                # Per-session token metrics (labeled)
                for s in sessions:
                    # Prefer 'key' for readability, fallback to 'sessionId' or 'unknown'
                    s_id = str(s.get('key') or s.get('sessionId') or 'unknown').replace('"', '\\"')
                    model = str(s.get('model', 'unknown')).replace('"', '\\"')
                    labels = f'session="{s_id}",model="{model}"'
                    
                    in_tok = s.get('inputTokens', 0) or 0
                    out_tok = s.get('outputTokens', 0) or 0
                    
                    metrics.append(f'openclaw_tokens_input_total{{{labels}}} {in_tok}')
                    metrics.append(f'openclaw_tokens_output_total{{{labels}}} {out_tok}')
                
                self.wfile.write('\n'.join(metrics).encode('utf-8') + b'\n')
            except Exception as e:
                self.wfile.write(f'# Error: {str(e)}'.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8000), MetricsHandler)
    print("OpenClaw Exporter started on port 8000")
    server.serve_forever()
