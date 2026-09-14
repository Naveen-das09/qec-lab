import io
import json
import subprocess
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from qec import server
from qec.engine import Experiment


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path)
    monkeypatch.setattr(server, "API_KEY", "")
    with TestClient(server.app) as client:
        yield client
        for _ in range(200):
            if not server.CANCEL:
                break
            time.sleep(0.01)


def wait_for_run(client, run_id):
    for _ in range(300):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("running", "queued"):
            return run
        time.sleep(0.02)
    pytest.fail("Run did not terminate")


def test_projects_isolate_runs_drafts_and_reports(client):
    project = client.post('/api/projects', json={'name':'Noise study', 'notes':'Compare measurement noise.'}).json()
    pid = project['id']
    spec = Experiment(distances=[3], probabilities=[0.005], shots=1000).model_dump()
    assert client.post('/api/draft?project_id=' + pid, json=spec).status_code == 200
    assert client.get('/api/draft').json() is None
    assert client.get('/api/draft?project_id=' + pid).json() == spec
    r = client.post('/api/runs?project_id=' + pid, json=spec)
    run = wait_for_run(client, r.json()['id'])
    assert run['project_id'] == pid
    assert client.get('/api/runs?project_id=default').json() == []
    assert len(client.get('/api/runs?project_id=' + pid).json()) == 1
    updated = client.put('/api/projects/' + pid, json={'name':'Revised study','notes':'Researcher observation'})
    assert updated.status_code == 200
    report = client.get('/api/projects/' + pid + '/report')
    assert report.status_code == 200
    assert 'Researcher observation' in report.text
    assert 'Revised study' in report.text
    assert run['id'] in report.text


def test_legacy_runs_remain_in_default_project(client):
    response = client.post('/api/runs', json={'distances':[3], 'shots':1000, 'probabilities':[0]})
    run = wait_for_run(client, response.json()['id'])
    del run['project_id']
    server.save(run)
    assert client.get('/api/runs/' + run['id']).json()['project_id'] == 'default'
    assert client.get('/api/runs?project_id=default').json()[0]['id'] == run['id']


def test_unknown_projects_and_blank_names_rejected(client):
    assert client.post('/api/projects', json={'name':'   '}).status_code == 422
    assert client.post('/api/runs?project_id=missing', json={}).status_code == 404
    assert client.get('/api/draft?project_id=missing').status_code == 404
    assert client.get('/api/projects/missing/report').status_code == 404


def test_queue_cancellation_preserves_project_and_partial_record(client, monkeypatch):
    submitted = []
    class HeldWorker:
        def submit(self, fn, *args):
            submitted.append((fn, args))
    monkeypatch.setattr(server, 'POOL', HeldWorker())
    pid = client.post('/api/projects', json={'name':'Queued study'}).json()['id']
    rid = client.post('/api/runs?project_id=' + pid, json={'distances':[3], 'shots':1000}).json()['id']
    try:
        jobs = client.get('/api/queue').json()
        assert jobs[0]['id'] == rid and jobs[0]['project_id'] == pid
        assert client.post('/api/runs/' + rid + '/cancel').status_code == 200
        assert server.CANCEL[rid].is_set()
        fn, args = submitted[0]
        fn(*args)
        run = client.get('/api/runs/' + rid).json()
        assert run['status'] == 'cancelled'
        assert run['project_id'] == pid
        assert client.get('/api/queue').json() == []
    finally:
        server.CANCEL.pop(rid, None)


def test_project_draft_conversations_are_scoped(client, monkeypatch):
    seen = []
    def chat(key, message, spec, run, history):
        seen.append(history)
        return {'answer':'Review your plan.', 'proposal':None, 'trace':[], 'model':'test'}
    monkeypatch.setattr(server.agent, 'chat', chat)
    pid = client.post('/api/projects', json={'name':'Assistant study'}).json()['id']
    payload = {'message':'Stage a plan', 'spec':{}, 'project_id':pid}
    assert client.post('/api/assistant', json=payload).status_code == 200
    assert client.get('/api/messages?scope=draft').json() == []
    assert len(client.get('/api/messages?scope=draft:' + pid).json()) == 1
    assert client.post('/api/assistant', json=payload).status_code == 200
    assert len(seen[1]) == 1


def test_run_export_and_exact_replay(client, tmp_path):
    response = client.post(
        "/api/runs", json={"distances": [3], "probabilities": [0.005], "shots": 1000}
    )
    assert response.status_code == 201
    run = wait_for_run(client, response.json()["id"])
    assert run["status"] == "completed"
    assert run["points"][0]["shots"] == 1000
    exported = client.get(f'/api/runs/{run["id"]}/export')
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert {
            "run.json",
            "spec.json",
            "report.md",
            "results.csv",
            "requirements.txt",
            "replay.py",
        } <= set(archive.namelist())
        root = tmp_path / "replay"
        archive.extractall(root)
        assert json.loads(archive.read("run.json"))["points"] == run["points"]
    result = subprocess.run(
        [sys.executable, str(root / "replay.py")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "saved" in result.stdout
    assert client.get("/api/runs").json()[0]["id"] == run["id"]
    assert "Interpretation limits" in client.get(f'/api/runs/{run["id"]}/report').text


def test_validation_security_and_no_key(client):
    assert client.post("/api/runs", json={"distances": [2]}).status_code == 422
    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert (
        client.post(
            "/api/runs", json={}, headers={"Origin": "https://external.example"}
        ).status_code
        == 403
    )
    assert (
        client.get("/api/health", headers={"Host": "external.example"}).status_code
        == 400
    )
    response = client.post(
        "/api/assistant",
        json={"message": "Plan a run", "spec": Experiment().model_dump()},
    )
    assert response.status_code == 400 and "Connect" in response.json()["detail"]
    assert client.get("/.env").status_code == 404
    assert client.get("/data/qec.sqlite3").status_code == 404


def test_saved_draft_and_key_not_returned(client):
    spec = Experiment(title="Persist this draft").model_dump()
    assert client.post("/api/draft", json=spec).status_code == 200
    assert client.get("/api/draft").json() == spec
    assert (
        client.post("/api/settings", json={"api_key": "test-key-not-real"}).status_code
        == 200
    )
    health = client.get("/api/health")
    assert health.json()["gemini_connected"]
    assert "test-key-not-real" not in health.text
    assert client.post("/api/settings", json={"api_key": ""}).status_code == 200


def test_restart_marks_interrupted(client):
    run = {
        "id": "restart-fixture",
        "created": server.now(),
        "status": "running",
        "events": [],
        "points": [],
    }
    server.save(run)
    with TestClient(server.app):
        assert server.get_run(run["id"])["status"] == "interrupted"


def test_assistant_conversation_persists(client, monkeypatch):
    monkeypatch.setattr(
        server.agent,
        "chat",
        lambda *args: {
            "answer": "Review the evidence",
            "proposal": None,
            "trace": ["Read measured evidence"],
            "model": "test",
        },
    )
    assert (
        client.post(
            "/api/assistant",
            json={"message": "Explain", "spec": Experiment().model_dump()},
        ).status_code
        == 200
    )
    saved = client.get("/api/messages?scope=draft").json()
    assert saved[0]["message"] == "Explain"
    assert saved[0]["answer"] == "Review the evidence"
    assert client.get("/api/messages?scope=different-run").json() == []
