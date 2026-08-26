from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "playground" / "smoke_api"


def request(url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health(base: str) -> None:
    deadline = time.time() + 8
    last_error = None
    while time.time() < deadline:
        try:
            health = request(f"{base}/api/health")
            assert health["ok"] is True
            return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"server did not become healthy: {last_error}")


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    home = SCRATCH / f"chatassign-{int(time.time() * 1000)}"
    proc = None
    try:
        port = "8876"
        proc = subprocess.Popen(
            [sys.executable, "-m", "chatassign.server", "--host", "127.0.0.1", "--port", port, "--home", str(home)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        base = f"http://127.0.0.1:{port}"
        wait_for_health(base)
        events = request(f"{base}/api/events/candidates")["events"]
        assert any(event["event_id"] == "evt_voice_thought_001" for event in events)
        policies = request(f"{base}/api/policies")["policies"]
        assert policies[0]["policy_id"] == "voice-thought"
        backends = request(f"{base}/api/backends")["backends"]
        assert backends[0]["backend_id"] == "local-chatboard-mock"
        contracts = request(f"{base}/api/contracts")
        assert "waiting_for_confirmation" in contracts["state_machine"]["states"]
        assert contracts["event_consumer"]["zulip_filter"]["owner"].startswith("ChatAssign")
        assert contracts["chatboard_http_client"]["create_task"].startswith("POST /api/tasks")

        ignored = request(f"{base}/api/events/ingest", {"source": "voice", "tags": ["reference"], "event_id": "evt_ignored"})
        assert ignored["accepted"] is False
        ingested = request(
            f"{base}/api/events/ingest",
            {
                "source": "voice",
                "tags": ["sort"],
                "event_id": "evt_voice_sort_alias",
                "title": "Voice thought through trigger alias",
            },
        )
        assert ingested["accepted"] is True
        assert ingested["assignment"]["state"] == "waiting_for_user"

        assignment = request(
            f"{base}/api/assignments",
            {"event_id": "evt_voice_thought_001", "policy_id": "voice-thought"},
        )
        assert assignment["status"] == "waiting_for_user"
        assert assignment["state"] == "waiting_for_user"
        assert assignment["privacy"]["stored_full_transcript"] is False
        assert assignment["paths"]["local"]["report_path"].endswith("result.md")
        assert "report_url" in assignment["paths"]["public"]
        assert assignment["watch"]["source"] == "zulip"
        assert assignment["links"]["task_url"] is None

        routed = request(
            f"{base}/api/assignments/{assignment['assignment_id']}/route",
            {"backend_id": "local-chatboard-mock", "executor": "codex"},
        )
        assert routed["route"]["executor"] == "codex"

        try:
            request(f"{base}/api/assignments/{assignment['assignment_id']}/dispatch", {})
            raise AssertionError("dispatch should require explicit confirmation")
        except urllib.error.HTTPError as exc:
            assert exc.code == 409

        refined = request(
            f"{base}/api/assignments/{assignment['assignment_id']}/reply",
            {"content": "Keep Event payload metadata-only and postpone ChatBoard creation while the draft is still being shaped."},
        )
        assert refined["state"] == "waiting_for_confirmation"
        assert refined["draft"]["version"] == 2
        ignored_zulip = request(
            f"{base}/api/events/ingest",
            {
                "assignment_id": assignment["assignment_id"],
                "source": "zulip",
                "event_id": "evt_zulip_other_sender",
                "sender_email": "other@example.invalid",
                "content": "This should not refine the assignment.",
            },
        )
        assert ignored_zulip["accepted"] is False

        confirmed = request(
            f"{base}/api/assignments/{assignment['assignment_id']}/confirm",
            {"content": "Confirmed. Create the task and run."},
        )
        assert confirmed["status"] == "running"
        assert confirmed["run"]["backend_session_id"].startswith("mock_session_")
        assert confirmed["route"]["board_task_id"].startswith("task_")
        assert confirmed["links"]["task_url"]
        assert confirmed["links"]["prd_url"]

        progress = request(f"{base}/api/assignments/{assignment['assignment_id']}/progress", {"content": "Any update?"})
        assert "progress_answer" in progress["bot_messages"]

        done = request(f"{base}/api/assignments/{assignment['assignment_id']}/complete", {"status": "completed"})
        assert done["status"] == "followup_monitoring"
        assert done["run"]["status"] == "completed"

        html = urllib.request.urlopen(f"{base}/", timeout=5).read().decode("utf-8")
        assert "ChatAssign Control Plane" in html
        assert "Inbox" in html and "Assignments" in html and "Assignment Loop Detail" in html
        print("PASS smoke_api")
        print(f"data_root={home}")
        return 0
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            if proc.returncode not in (0, -15):
                stdout, stderr = proc.communicate()
                print(stdout)
                print(stderr, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
