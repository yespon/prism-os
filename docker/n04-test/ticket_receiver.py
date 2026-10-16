"""Owned HTTPS test receiver: persistent counts without bodies or secrets."""

import hashlib
import hmac
import json
import os
import sqlite3
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class ReceiptStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS receipts (id INTEGER PRIMARY KEY, key_hash TEXT, body_hash TEXT NOT NULL, ticket_id TEXT NOT NULL, mode TEXT NOT NULL, received_at REAL NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def record(self, body, key, mode):
        digest = hashlib.sha256(body).hexdigest()
        key_hash = hashlib.sha256(key.encode()).hexdigest() if key else None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT body_hash,ticket_id FROM receipts WHERE key_hash=? ORDER BY id LIMIT 1', (key_hash,)).fetchone() if key_hash else None
            if previous and previous[0] != digest:
                return None
            count = db.execute('SELECT count(*) FROM receipts').fetchone()[0]
            ticket = previous[1] if previous else f'N04-{count + 1}'
            db.execute('INSERT INTO receipts(key_hash,body_hash,ticket_id,mode,received_at) VALUES(?,?,?,?,?)', (key_hash, digest, ticket, mode, time.time()))
            return ticket

    def stats(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,ticket_id,mode,received_at FROM receipts ORDER BY id').fetchall()
        return {'request_count': len(rows), 'distinct_ticket_count': len({r[1] for r in rows}), 'receipts': [{'sequence': r[0], 'ticket_id': r[1], 'mode': r[2], 'received_at': r[3]} for r in rows]}


def make_server(address, store, token, mode_path):
    if not token:
        raise ValueError('Receiver token required')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(data)
            except OSError:
                pass

        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + token).encode())

        def do_GET(self):
            if self.path == '/health':
                return self.reply(200, {'status': 'ok'})
            if not self.authorized():
                return self.reply(401, {'status': 'unauthorized'})
            if self.path != '/stats':
                return self.reply(404, {'status': 'unavailable'})
            return self.reply(200, store.stats())

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {'status': 'unauthorized'})
            if self.path != '/tickets':
                return self.reply(404, {'status': 'unavailable'})
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                    raise ValueError
                length = int(lengths[0])
                if not 0 < length <= 1024 * 1024:
                    raise ValueError
                self.connection.settimeout(5)
                body = self.rfile.read(length)
                if len(body) != length or not isinstance(json.loads(body), dict):
                    raise ValueError
                mode = Path(mode_path).read_text().strip()
                if mode not in {'ok', 'fail', 'timeout'}:
                    raise ValueError
                key = self.headers.get('Idempotency-Key', '')
                if len(key) > 1024:
                    raise ValueError
            except (ValueError, OSError):
                return self.reply(400, {'status': 'invalid'})
            ticket = store.record(body, key, mode)
            if ticket is None:
                return self.reply(409, {'status': 'idempotency_conflict'})
            if mode == 'timeout':
                time.sleep(35)
            if mode == 'fail':
                return self.reply(503, {'status': 'injected_failure'})
            return self.reply(200, {'id': ticket})

    return ThreadingHTTPServer(address, Handler)


def main():
    runtime = Path(os.environ.get('N04_RECEIVER_HOME', '/state'))
    token = (runtime / 'receiver-token').read_text().strip()
    server = make_server(('0.0.0.0', 8443), ReceiptStore(runtime / 'receipts.db'), token, runtime / 'receiver-mode')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(runtime / 'server.crt', runtime / 'server.key')
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
