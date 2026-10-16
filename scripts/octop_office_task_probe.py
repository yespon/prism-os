"""Real configured model Office task via the same authenticated APIs as the Web UI.

Credentials/transcripts stay in the ignored owned WSL runtime. Public receipts
contain only test content, identifiers and outcomes, never tokens/model config.
"""
import argparse
import hashlib
import io
import json
import secrets
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'backend/tmp/n04-wsl'
BASE = 'http://127.0.0.1:18026'


def execute(output: Path, resume: Path | None = None):
    assert not output.exists(), 'Keep prior receipts'
    fixture = json.loads((STATE / 'live-fixture.json').read_text())
    suffix = secrets.token_hex(5)
    private = STATE / ('office-task-' + suffix)
    private.mkdir(mode=0o700)
    result = {'complete': False, 'configured_model': fixture['model_name'], 'simulated_model': False, 'private_diagnostics': str(private), 'phases': []}
    clients = []

    def call(client, path, body=None, method=None, status=200, **kwargs):
        response = client.request(method or ('POST' if body is not None else 'GET'), path, json=body, **kwargs)
        assert response.status_code == status, (path, response.status_code)
        return response.json()

    def login(role):
        account = fixture['users'][role]
        client = httpx.Client(base_url=BASE, headers={'X-Tenant-Id': fixture['other_tenant_id'] if role == 'outsider' else fixture['tenant_id']}, trust_env=False, timeout=240)
        clients.append(client)
        session = call(client, '/api/auth/login', {'email': account['email'], 'password': account['password']})
        client.headers['Authorization'] = 'Bearer ' + session['session']['token']
        return client

    def checkpoint():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')

    try:
        owner, requester, outsider = [login(role) for role in ['approver', 'requester', 'outsider']]
        if resume is None:
            agent = call(requester, '/api/agents', {'name': 'office-task-' + suffix, 'description': 'Office user-task acceptance', 'model': fixture['model_name'], 'tool_groups': [], 'skills': [], 'system_prompt': '完成用户要求的文档任务。必须先 read_file 读取附件，再用 office_docx 创建文档，最后 present_files 展示文件。不要使用 bash，不要委派。'}, status=201)
            thread = call(requester, '/api/langgraph/threads', {})['thread_id']
            result.update({'agent_id': agent['id'], 'agent_name': agent['name'], 'thread_id': thread})
            graph = '/api/langgraph/threads/' + thread
            brief = '项目：PrismOS 集成验收\n已完成：恢复服务后的真实模型任务\n待办：完整 Office 与专家任务\n验收标识：OFFICE_TASK_' + suffix
            response = requester.post('/api/threads/' + thread + '/uploads', files={'files': ('brief.txt', brief.encode(), 'text/plain')})
            assert response.status_code == 200, ('upload', response.status_code)
            uploaded = response.json()['files'][0]
            result['phases'].append('native_login_agent_thread_upload')
            output_path = '/mnt/user-data/outputs/report-' + suffix + '.docx'
            task = '读取附件 ' + uploaded['virtual_path'] + '，按附件事实制作中文项目进度 DOCX：标题“集成进度报告”，正文含已完成、待办和原样验收标识，一张表列出已完成与待办。调用 office_docx action=create，output_path=' + output_path + '。成功后调用 present_files，paths=[' + json.dumps(output_path) + ']，回复下载链接。'
            attachment = {'attachment_id': uploaded['attachment_id']}
            payload = {'assistant_id': 'lead_agent', 'input': {'messages': [{'type': 'human', 'content': task, 'additional_kwargs': {'attachments': [attachment]}}]}, 'context': {'agent_name': agent['name'], 'model_name': fixture['model_name'], 'thinking_enabled': False, 'is_plan_mode': False, 'subagent_enabled': False, 'referenced_attachments': [attachment]}, 'config': {'recursion_limit': 30}, 'stream_mode': ['values', 'updates'], 'stream_subgraphs': True}
            with requester.stream('POST', graph + '/runs/stream', json=payload) as response:
                assert response.status_code == 200, ('run', response.status_code)
                transcript = '\n'.join(response.iter_lines())
            saved = private / 'stream.txt'
            saved.write_text(transcript)
            saved.chmod(0o600)
            result['stream_received'] = True
            checkpoint()
        else:
            previous = json.loads(resume.read_text())
            assert previous.get('stream_received') and {'read_file', 'office_docx', 'present_files'}.issubset(previous['tool_names'])
            result.update({key: previous[key] for key in ['agent_id', 'agent_name', 'thread_id']})
            result['reused_model_execution_receipt'] = str(resume)
            suffix = previous['agent_name'].removeprefix('office-task-')
            thread = previous['thread_id']
        graph = '/api/langgraph/threads/' + thread
        output_path = '/mnt/user-data/outputs/report-' + suffix + '.docx'
        state = call(requester, graph + '/state')
        saved = private / 'state.json'
        saved.write_text(json.dumps(state, ensure_ascii=False))
        saved.chmod(0o600)
        messages = state.get('values', {}).get('messages', [])
        calls = [item for message in messages for item in message.get('tool_calls', [])]
        tool_messages = [m for m in messages if m.get('type') == 'tool']
        result['tool_names'] = [item.get('name') for item in calls]
        result['tool_outcomes'] = [{'name': m.get('name'), 'status': m.get('status'), 'content_type': type(m.get('content')).__name__} for m in tool_messages]
        checkpoint()
        assert {'read_file', 'office_docx', 'present_files'}.issubset(result['tool_names']), 'Required actual model tools missing'
        artifact = '/api/threads/' + thread + '/artifacts' + output_path + '?download=true'
        response = requester.get(artifact)
        assert response.status_code == 200, ('artifact', response.status_code)
        data = response.content
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            root = ET.fromstring(package.read('word/document.xml'))
            text = ''.join(root.itertext())
            assert all(value in text for value in ['集成进度报告', 'OFFICE_TASK_' + suffix, '恢复服务', 'Office'])
            assert root.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl')
        digest = hashlib.sha256(data).hexdigest()
        assert 'no-store' in {v.strip() for v in response.headers['cache-control'].split(',')}
        assert outsider.get(artifact).status_code == 404
        assert owner.get(artifact).status_code == 404, 'Tenant administrator does not own this private thread'
        assert outsider.get(graph + '/state').status_code == 404
        assert owner.get(graph + '/state').status_code == 404
        result['phases'].append('real_model_read_create_present_download_acl')
        requester.close()
        requester = login('requester')
        history = call(requester, graph + '/history', {'limit': 10})
        assert history and output_path in json.dumps(history)
        again = requester.get(artifact)
        assert again.status_code == 200 and hashlib.sha256(again.content).hexdigest() == digest
        assert 'office_docx' in json.dumps(call(requester, graph + '/state'))
        result.update({'complete': True, 'artifact_url': artifact, 'artifact_sha256': digest, 'artifact_bytes': len(data), 'document_text_and_table_verified': True, 'fresh_session_history_and_download': True, 'cross_tenant_and_nonowner_denied': True, 'raw_transcript_exported': False})
        result['phases'].append('fresh_session_history_artifact')
    except Exception as error:
        result['failure_type'] = type(error).__name__
        result['failure'] = str(error)
        raise
    finally:
        for client in clients:
            client.close()
        checkpoint()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', type=Path, help='Recheck an already executed model task; never resend the model request')
    args = parser.parse_args()
    execute(args.output, args.resume)
