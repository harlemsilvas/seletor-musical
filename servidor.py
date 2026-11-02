#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import functools
import sys

ROOT = Path(__file__).resolve().parent / 'web'
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

if __name__ == '__main__':
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8765), functools.partial(Handler, directory=str(ROOT)))
    except OSError as error:
        sys.exit(f'Não foi possível abrir a porta 8765: {error}')
    print('Minha seleção musical: http://localhost:8765 (Ctrl+C para parar)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
