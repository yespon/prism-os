"""Actual TLS receiver, durable independent counts, admission and timeout facts."""

import concurrent.futures
import importlib.util
import json
import ssl
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('n04_receiver', ROOT / 'docker/n04-test/ticket_receiver.py')
receiver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receiver)


@pytest.fixture
def endpoint(tmp_path):
    cert, key = tmp_path / 'cert.pem', tmp_path / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True)
    store = receiver.ReceiptStore(tmp_path / 'receipts.db')
    mode = tmp_path / 'mode'
    mode.write_text('ok')
    server = receiver.make_server(('127.0.0.1', 0), store, 'private-receiver-token', mode)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(base_url=f'https://127.0.0.1:{server.server_port}', verify=ssl.create_default_context(cafile=str(cert)), headers={'Authorization': 'Bearer private-receiver-token'}, trust_env=False) as client:
        yield client, store, mode
    server.shutdown()
    server.server_close()
    thread.join(5)
    assert not thread.is_alive()


def test_actual_tls_counts_repeated_requests_separately_from_unique_tickets(endpoint):
    client, store, _ = endpoint
    first = client.post('/tickets', json={'description': 'private-payload'}, headers={'Idempotency-Key': 'private-key'})
    second = client.post('/tickets', json={'description': 'private-payload'}, headers={'Idempotency-Key': 'private-key'})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {'id': 'N04-1'}
    stats = client.get('/stats').json()
    assert stats['request_count'] == 2 and stats['distinct_ticket_count'] == 1
    assert receiver.ReceiptStore(store.path).stats() == stats
    db_bytes = Path(store.path).read_bytes()
    assert all(secret not in db_bytes for secret in [b'private-receiver-token', b'private-payload', b'private-key'])
    assert all(secret not in json.dumps(stats) for secret in ['private-receiver-token', 'private-payload', 'private-key'])


def test_actual_tls_unauthorized_invalid_or_conflicting_requests_have_no_ticket(endpoint):
    client, store, _ = endpoint
    assert client.get('/health', headers={'Authorization': ''}).status_code == 200
    assert client.get('/stats', headers={'Authorization': ''}).status_code == 401
    assert client.post('/tickets', json={}, headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.post('/tickets?secret=not-logged', json={}).status_code == 404
    assert client.post('/tickets', content=b'not-json').status_code == 400
    assert client.post('/tickets', json=[]).status_code == 400
    assert store.stats()['request_count'] == 0
    assert client.post('/tickets', json={'n': 1}, headers={'Idempotency-Key': 'same'}).status_code == 200
    assert client.post('/tickets', json={'n': 2}, headers={'Idempotency-Key': 'same'}).status_code == 409
    assert store.stats()['request_count'] == 1


def test_parallel_actual_https_calls_preserve_every_request_and_one_ticket(endpoint):
    client, store, _ = endpoint
    def send(_):
        return client.post('/tickets', json={'value': 1}, headers={'Idempotency-Key': 'concurrent'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, range(8)))
    assert all(r.status_code == 200 and r.json()['id'] == 'N04-1' for r in responses)
    assert store.stats()['request_count'] == 8
    assert store.stats()['distinct_ticket_count'] == 1


def test_actual_http_failure_is_counted_before_response(endpoint):
    client, store, mode = endpoint
    mode.write_text('fail')
    assert client.post('/tickets', json={}).status_code == 503
    assert store.stats()['request_count'] == 1
    assert store.stats()['receipts'][0]['mode'] == 'fail'


def test_actual_client_timeout_does_not_erase_received_request(endpoint):
    client, store, mode = endpoint
    mode.write_text('timeout')
    with pytest.raises(httpx.ReadTimeout):
        client.post('/tickets', json={}, timeout=0.2)
    assert store.stats()['request_count'] == 1
    assert store.stats()['receipts'][0]['mode'] == 'timeout'


def test_unknown_fault_mode_fails_closed_without_recording(endpoint):
    client, store, mode = endpoint
    mode.write_text('arbitrary')
    assert client.post('/tickets', json={}).status_code == 400
    assert store.stats()['request_count'] == 0


def test_empty_receiver_credential_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='token required'):
        receiver.make_server(('127.0.0.1', 0), receiver.ReceiptStore(tmp_path / 'test.db'), '', tmp_path / 'mode')


@pytest.mark.parametrize("state", ["missing_owner", "wrong_owner", "symlink"])
def test_management_refuses_unowned_runtime_without_invoking_compose(tmp_path, monkeypatch, state):
    spec = importlib.util.spec_from_file_location('n04_env_test', ROOT / 'scripts/octop_wsl_test_env.py')
    environment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(environment)
    target = tmp_path / 'backend/tmp/n04-wsl'
    target.mkdir(parents=True)
    if state == 'wrong_owner':
        (target / 'owner').write_text('other-project')
    elif state == 'symlink':
        other = tmp_path / 'other-project'
        other.mkdir()
        (other / 'owner').write_text(environment.MARKER)
        target.rmdir()
        target.symlink_to(other)
    monkeypatch.setattr(environment, 'ROOT', tmp_path)
    monkeypatch.setattr(environment, 'STATE', target)
    monkeypatch.setattr(sys, 'argv', ['octop_wsl_test_env.py', 'stop'])
    def forbidden(*args, **kwargs):
        pytest.fail('Compose must not touch an unowned runtime')
    monkeypatch.setattr(environment.subprocess, 'run', forbidden)
    with pytest.raises((ValueError, FileNotFoundError)):
        environment.main()
