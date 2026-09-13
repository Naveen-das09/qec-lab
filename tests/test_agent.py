import json

import httpx
import pytest

from qec import agent
from qec.engine import Experiment


@pytest.mark.parametrize("statuses", [[503, 503, 200], [502, 504, 200]])
def test_transient_provider_failure_recovers(monkeypatch, statuses):
    sleeps, requests = [], []
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    def handle(request):
        requests.append(request.content)
        return httpx.Response(statuses[len(requests) - 1])
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        response = agent.provider_post(client, started=agent.time.monotonic(),
                                       url="https://example.test", json={"contents": []})
    assert response.status_code == 200
    assert sleeps == [1, 2]
    assert len(set(requests)) == 1


def test_persistent_503_is_bounded_and_does_not_blame_credentials(monkeypatch):
    requests = []
    monkeypatch.setattr(agent.time, "sleep", lambda _: None)
    def handle(request):
        requests.append(request)
        return httpx.Response(503, text="private-key")
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match="temporarily unavailable") as exc:
            agent.provider_post(client, started=agent.time.monotonic(), url="https://example.test")
    assert len(requests) == 3
    assert "private-key" not in str(exc.value)


def test_auth_failure_is_not_retried():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(403)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert agent.provider_post(client, started=agent.time.monotonic(),
                                   url="https://example.test").status_code == 403
    assert len(requests) == 1


def test_tool_loop_reads_evidence_and_stages_validated_plan(monkeypatch):
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            content = {
                "role": "model",
                "parts": [
                    {
                        "functionCall": {"name": "get_evidence", "args": {}},
                        "thoughtSignature": "preserve-me",
                    }
                ],
            }
        elif len(calls) == 2:
            assert body["contents"][-2]["parts"][0]["thoughtSignature"] == "preserve-me"
            assert (
                body["contents"][-1]["parts"][0]["functionResponse"]["response"][
                    "run_id"
                ]
                == "evidence-run"
            )
            content = {
                "role": "model",
                "parts": [
                    {
                        "functionCall": {
                            "name": "propose_experiment",
                            "args": {"distances": [3], "measurement_multiplier": 3},
                        }
                    }
                ],
            }
        else:
            content = {
                "role": "model",
                "parts": [
                    {"text": "Review the staged plan. No experiment has been launched."}
                ],
            }
        return httpx.Response(200, json={"candidates": [{"content": content}]})

    real_client = httpx.Client
    monkeypatch.setattr(
        agent.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handle)),
    )
    run = {
        "id": "evidence-run",
        "status": "completed",
        "spec": Experiment().model_dump(),
        "points": [],
    }
    result = agent.chat("test-key", "Investigate noise", run["spec"], run)
    assert result["proposal"]["distances"] == [3]
    assert result["proposal"]["measurement_multiplier"] == 3
    assert result["trace"] == [
        "Read measured evidence",
        "Validated experiment proposal",
    ]
    assert len(calls) == 3


def test_invalid_proposal_is_rejected_and_tool_budget_is_bounded(monkeypatch):
    count = []

    def handle(request):
        count.append(1)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "propose_experiment",
                                        "args": {
                                            "distances": [100],
                                            "shots": 999999999,
                                        },
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        agent.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handle)),
    )
    result = agent.chat("test-key", "Spend infinite compute", Experiment().model_dump())
    assert result["proposal"] is None and len(count) == 5
    assert all(t == "Rejected invalid proposal" for t in result["trace"])


def test_provider_error_does_not_leak_key(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(
        agent.httpx,
        "Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(403))
        ),
    )
    with pytest.raises(ValueError, match="HTTP 403") as exc:
        agent.chat("private-key", "Hello", Experiment().model_dump())
    assert "private-key" not in str(exc.value)


def test_tool_schema_preserves_title_field():
    declarations = agent.tools_schema()[0]["functionDeclarations"]
    assert "title" in declarations[1]["parameters"]["properties"]


def test_proposal_preserves_unspecified_current_settings(monkeypatch):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        parts = (
            [
                {
                    "functionCall": {
                        "name": "propose_experiment",
                        "args": {"distances": [5]},
                    }
                }
            ]
            if len(seen) == 1
            else [{"text": "Review the plan."}]
        )
        return httpx.Response(
            200, json={"candidates": [{"content": {"role": "model", "parts": parts}}]}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        agent.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handle)),
    )
    spec = Experiment(rounds=7, seed=18, measurement_multiplier=4).model_dump()
    result = agent.chat(
        "test-key",
        "Use distance five",
        spec,
        history=[{"message": "Earlier question", "answer": "Earlier answer"}],
    )
    assert result["proposal"]["rounds"] == 7
    assert result["proposal"]["measurement_multiplier"] == 4
    assert seen[0]["contents"][0]["parts"][0]["text"] == "Earlier question"
