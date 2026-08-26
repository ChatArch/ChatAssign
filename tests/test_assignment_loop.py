from __future__ import annotations

import sys
from pathlib import Path

import chatassign.server as server_module
from chatassign.server import (
    Store,
    complete_assignment,
    confirm_assignment,
    create_assignment,
    is_confirmation_text,
    refine_from_reply,
    route_assignment,
    voice_event_matches_policy,
    zulip_event_from_rex,
)


def test_voice_trigger_alias_policy() -> None:
    assert voice_event_matches_policy({"source": "voice", "tags": ["thought"]})
    assert voice_event_matches_policy({"source": "voice", "tags": ["sort"]})
    assert not voice_event_matches_policy({"source": "manual", "tags": ["thought"]})
    assert not voice_event_matches_policy({"source": "voice", "tags": ["reference"]})


def test_zulip_sender_filter_is_chatassign_policy(tmp_path: Path) -> None:
    store = Store(tmp_path / "state")
    assignment = create_assignment(store, {"event_id": "evt_voice_thought_001"})
    assert zulip_event_from_rex({"source": "zulip", "sender_email": "rex@example.invalid"}, assignment)
    assert not zulip_event_from_rex({"source": "zulip", "sender_email": "assignment-bot@example.invalid"}, assignment)
    assert not zulip_event_from_rex({"source": "zulip", "sender_email": "someone@example.invalid"}, assignment)


def test_confirmation_text_requires_explicit_approval() -> None:
    assert is_confirmation_text("Confirmed. Create the task and run.")
    assert is_confirmation_text("I approve this, go ahead.")
    assert is_confirmation_text("确认创建任务")

    assert not is_confirmation_text("Please confirm scope, backend target, and whether this should stay mock.")
    assert not is_confirmation_text("Keep metadata-only events and ask me to confirm before creating the task.")
    assert not is_confirmation_text("Before confirmation, refine the draft and do not dispatch yet.")


def test_assignment_state_machine_confirmation_gate(tmp_path: Path) -> None:
    store = Store(tmp_path / "state")
    assignment = create_assignment(store, {"event_id": "evt_voice_thought_001"})
    assert assignment["state"] == "waiting_for_user"
    assert assignment["links"]["task_url"] is None

    assignment = refine_from_reply(store, assignment, {"content": "Keep metadata-only events and ask me before creating the task."})
    assert assignment["state"] == "waiting_for_confirmation"
    assert assignment["draft"]["last_user_reply_event_id"].startswith("evt_zulip_reply_")

    assignment = refine_from_reply(
        store,
        assignment,
        {"content": "Please confirm scope later; for now refine the draft and do not create the task."},
    )
    assert assignment["state"] == "waiting_for_confirmation"
    assert assignment["links"]["task_url"] is None

    assignment = confirm_assignment(store, assignment, {"content": "Confirmed."})
    assert assignment["state"] == "running"
    assert assignment["links"]["task_url"]
    assert assignment["links"]["prd_url"]

    assignment = complete_assignment(store, assignment, "completed")
    assert assignment["state"] == "followup_monitoring"
    assert assignment["watch"]["state"] == "decayed"


def test_real_chatboard_route_uses_executor_token_without_mock_report(tmp_path: Path, monkeypatch) -> None:
    store = Store(tmp_path / "state")
    assignment = create_assignment(store, {"event_id": "evt_voice_thought_001"})
    assignment = route_assignment(
        store,
        assignment,
        {
            "backend_id": "chatboard-live",
            "executor": "cursor-agent",
            "backend_base_url": "https://board.example.invalid",
            "board_root": str(tmp_path),
            "mode": "real",
        },
    )
    prompt_path = Path(assignment["paths"]["local"]["prompt_path"])
    prompt_path.write_text("Reply exactly CHATASSIGN_REAL_RUN_OK.\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_http_json(base_url: str, path: str, payload=None, *, api_token=None, executor_token=None):
        calls.append(
            {
                "base_url": base_url,
                "path": path,
                "payload": payload,
                "api_token": api_token,
                "executor_token": executor_token,
            }
        )
        if path.startswith("/api/tasks"):
            return {
                "card": {"id": "card-real-run"},
                "task_link": {"public_url": "https://board.example.invalid/#/tasks/card-real-run"},
                "prd_link": {"public_url": "https://board.example.invalid/api/cards/card-real-run/files/content?path=PRD.md"},
            }
        if path.startswith("/api/runs"):
            return {
                "run": {
                    "run_id": "run-real-1",
                    "backend_session_id": None,
                    "status": "running",
                    "mode": "real",
                    "os_pid": 1234,
                    "process_session_id": "1234",
                    "workdir": str(tmp_path / "state" / "projects" / assignment["assign_project_id"]),
                    "prompt_path": str(prompt_path),
                    "report_path": str(tmp_path / "state" / "projects" / assignment["assign_project_id"] / "result.md"),
                    "public_links": {"run": {"public_url": "https://board.example.invalid/api/runs/run-real-1"}},
                }
            }
        raise AssertionError(path)

    monkeypatch.setattr(server_module, "_http_json", fake_http_json)
    monkeypatch.setenv("CHATASSIGN_CHATBOARD_API_TOKEN", "api-token")
    monkeypatch.setenv("CHATASSIGN_CHATBOARD_EXECUTOR_TOKEN", "executor-token")

    confirmed = confirm_assignment(store, assignment, {"content": "Confirmed."})

    run_call = next(call for call in calls if str(call["path"]).startswith("/api/runs"))
    assert run_call["api_token"] == "api-token"
    assert run_call["executor_token"] == "executor-token"
    assert run_call["payload"]["mode"] == "real"
    assert confirmed["run"]["run_id"] == "run-real-1"
    assert confirmed["run"]["status"] == "running"
    assert confirmed["links"]["run_url"] == "https://board.example.invalid/api/runs/run-real-1"
    report_path = Path(confirmed["paths"]["local"]["report_path"])
    assert not report_path.exists()
