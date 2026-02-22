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
                count = data.get('count', 0)
                total_input = sum(s.get('inputTokens', 0) or 0 for s in sessions)
                total_output = sum(s.get('outputTokens', 0) or 0 for s in sessions)
                
                now = time.time() * 1000
                active_1h = sum(1 for s in sessions if (now - s.get('updatedAt', 0)) < 3600000)
                
                metrics = [
                    f'openclaw_sessions_total {count}',
                    f'openclaw_tokens_input_total {total_input}',
                    f'openclaw_tokens_output_total {total_output}',
                    f'openclaw_sessions_active_1h {active_1h}'
                ]
                
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
