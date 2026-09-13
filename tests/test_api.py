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
