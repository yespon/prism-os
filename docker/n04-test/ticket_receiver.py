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
            previous = db.execute('SELECT count(*) FROM receipts').fetchone()[0]
            db.execute('CREATE TABLE IF NOT EXISTS counter_metadata (key TEXT PRIMARY KEY, value INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO counter_metadata(key,value) VALUES(?,?)', ('historical_v1_receipts', previous))

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def begin(self):
        with self.connect() as db:
            row = db.execute('INSERT INTO receipts(body_hash,ticket_id,mode,received_at) VALUES(?,?,?,?)', ('', '', 'received', time.time()))
            return row.lastrowid

    def reject(self, attempt, reason):
        with self.connect() as db:
            db.execute('UPDATE receipts SET mode=? WHERE id=?', (reason, attempt))

    def record(self, body, key, mode, *, attempt=None):
        if attempt is None:
            attempt = self.begin()
        digest = hashlib.sha256(body).hexdigest()
        key_hash = hashlib.sha256(key.encode()).hexdigest() if key else None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT body_hash,ticket_id FROM receipts WHERE key_hash=? AND ticket_id<>? ORDER BY id LIMIT 1', (key_hash, '')).fetchone() if key_hash else None
            if previous and previous[0] != digest:
                db.execute('UPDATE receipts SET key_hash=?,body_hash=?,mode=? WHERE id=?', (key_hash, digest, 'idempotency_conflict', attempt))
                return None
            ticket = previous[1] if previous else f'N04-{attempt}'
            db.execute('UPDATE receipts SET key_hash=?,body_hash=?,ticket_id=?,mode=? WHERE id=?', (key_hash, digest, ticket, mode, attempt))
            return ticket

    def stats(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,ticket_id,mode,received_at FROM receipts ORDER BY id').fetchall()
            historical = db.execute('SELECT value FROM counter_metadata WHERE key=?', ('historical_v1_receipts',)).fetchone()[0]
        return {'counter_version': 2, 'historical_v1_receipts': historical, 'request_count': len(rows),
            'distinct_ticket_count': len({r[1] for r in rows if r[1]}), 'receipts': [{'sequence': r[0], 'ticket_id': r[1],
            'mode': r[2], 'received_at': r[3]} for r in rows]}


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
            attempt = store.begin()
            if not self.authorized():
                store.reject(attempt, 'unauthorized')
                return self.reply(401, {'status': 'unauthorized'})
            if self.path != '/tickets':
                store.reject(attempt, 'not_found')
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
                store.reject(attempt, 'invalid')
                return self.reply(400, {'status': 'invalid'})
            ticket = store.record(body, key, mode, attempt=attempt)
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
