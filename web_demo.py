"""Local browser demo for the status investigation agent."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / 'web'
sys.path.insert(0, str(ROOT))

from agent import run_agent
from bonus.tools import BonusTools
from providers import Provider
from run import load_local_env
from status_tools import StatusTools


class DemoHandler(BaseHTTPRequestHandler):
    provider_name = None
    model = None
    max_steps = 6

    def _send(self, status, payload, content_type='application/json; charset=utf-8'):
        body = payload if isinstance(payload, bytes) else (
            json.dumps(payload, ensure_ascii=False).encode('utf-8')
            if isinstance(payload, (dict, list)) else str(payload).encode('utf-8')
        )
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path != '/':
            self._send(404, {'error': 'Not found'})
            return
        try:
            body = (WEB_ROOT / 'index.html').read_bytes()
            self._send(200, body, 'text/html; charset=utf-8')
        except OSError as exc:
            self._send(500, {'error': str(exc)})

    def do_POST(self):
        if urlparse(self.path).path != '/api/ask':
            self._send(404, {'error': 'Not found'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            data = json.loads(self.rfile.read(length).decode('utf-8'))
            question = data.get('question', '').strip()
            mode = data.get('mode', 'snapshot')
            bonus = bool(data.get('bonus', False))
            if not question:
                raise ValueError('Vui lòng nhập câu hỏi.')
            if len(question) > 2000:
                raise ValueError('Câu hỏi tối đa 2000 ký tự.')
            if mode not in ('snapshot', 'live'):
                raise ValueError('Mode không hợp lệ.')
            provider = Provider(self.provider_name, self.model)
            tools = BonusTools(mode) if bonus else StatusTools(mode)
            result = run_agent(question, provider, tools, max_steps=self.max_steps)
            self._send(200, result)
        except json.JSONDecodeError:
            self._send(400, {'status': 'error', 'error': 'JSON không hợp lệ.'})
        except Exception as exc:
            self._send(500, {'status': 'error', 'error': f'{type(exc).__name__}: {str(exc)[:300]}'})

    def log_message(self, fmt, *args):
        print(f'[web-demo] {self.address_string()} - {fmt % args}')


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    load_local_env()
    parser = argparse.ArgumentParser(description='Chạy web demo cho status agent')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--provider', default=None)
    parser.add_argument('--model', default=None)
    parser.add_argument('--max-steps', type=int, default=6)
    args = parser.parse_args()
    DemoHandler.provider_name = args.provider or __import__('os').getenv('PROVIDER', 'openrouter')
    DemoHandler.model = args.model or __import__('os').getenv('MODEL') or __import__('os').getenv('API_MODEL')
    DemoHandler.max_steps = args.max_steps
    if not DemoHandler.model:
        parser.error('Thiếu MODEL hoặc --model')
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f'Web demo: http://{args.host}:{args.port}')
    print('Chỉ bind localhost; API key không được gửi xuống trình duyệt.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nĐã dừng web demo.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
