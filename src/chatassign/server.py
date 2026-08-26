from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.parse import parse_qs, unquote, urlparse


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


ASSIGNMENT_STATES = [
    "voice_seen",
    "draft_opened",
    "waiting_for_user",
    "refining_from_user_reply",
    "waiting_for_confirmation",
    "confirmed",
    "board_task_created",
    "running",
    "needs_review",
    "completed",
    "blocked",
    "followup_monitoring",
]

TERMINALISH_STATES = {"needs_review", "completed", "blocked", "followup_monitoring"}
STATUSES = set(ASSIGNMENT_STATES) | {"proposed", "accepted", "done", "rejected"}
TRIGGER_TAG_ALIASES = {"thought": ["thought", "sort"]}
REX_IDENTITIES = {
    "sender_email": os.environ.get("CHATASSIGN_REX_ZULIP_EMAIL", "rex@example.invalid"),
    "sender_id": os.environ.get("CHATASSIGN_REX_ZULIP_USER_ID", "rex-demo"),
    "display_name": os.environ.get("CHATASSIGN_REX_ZULIP_NAME", "Rex Demo"),
}
ASSIGNMENT_BOT = {
    "bot_email": os.environ.get("CHATASSIGN_BOT_ZULIP_EMAIL", "assignment-bot@example.invalid"),
    "bot_name": os.environ.get("CHATASSIGN_BOT_NAME", "ChatAssign Bot"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def chatassign_home() -> Path:
    explicit = os.environ.get("CHATASSIGN_HOME")
    if explicit:
        return Path(explicit).expanduser()
    return Path(os.environ.get("CHATARCH_HOME", "~/.chatarch")).expanduser() / "chatassign"


def safe_json_loads(data: str | None, default: Any) -> Any:
    if not data:
        return default
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return default


@dataclass
class ResolverConfig:
    enabled: bool
    local_root: Path
    public_base_url: str | None
    source: str


def load_resolver_config(home: Path) -> ResolverConfig:
    public_base = os.environ.get("CHATASSIGN_PUBLIC_BASE_URL")
    local_root = Path(os.environ.get("CHATASSIGN_PUBLIC_LOCAL_ROOT", str(home))).expanduser()
    source = "env"

    config_path = Path(os.environ.get("CHATASSIGN_RESOLVER_CONFIG", str(home / "resolver.json"))).expanduser()
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            public_base = config.get("public_base_url") or public_base
            if config.get("local_root"):
                local_root = Path(config["local_root"]).expanduser()
            source = str(config_path)
        except (OSError, json.JSONDecodeError):
            source = f"{config_path} (unreadable)"

    return ResolverConfig(
        enabled=bool(public_base),
        local_root=local_root.resolve(),
        public_base_url=public_base.rstrip("/") if public_base else None,
        source=source,
    )


class LocalPublicResolver:
    def __init__(self, config: ResolverConfig):
        self.config = config

    def resolve(self, path: str | Path | None) -> str | None:
        if not path or not self.config.enabled or not self.config.public_base_url:
            return None
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.config.local_root / candidate
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(self.config.local_root)
        except (OSError, ValueError):
            return None
        parts = [quote_path_part(part) for part in relative.parts]
        return f"{self.config.public_base_url}/{'/'.join(parts)}"

    def status(self) -> dict[str, Any]:
        return {
            "kind": "config-driven-local-public-resolver",
            "enabled": self.config.enabled,
            "local_root": str(self.config.local_root),
            "public_base_url_configured": bool(self.config.public_base_url),
            "config_source": self.config.source,
            "chatboard_imported": False,
            "note": "Prototype resolver is swappable with ChatBoard's resolver when that import boundary is available.",
        }


def quote_path_part(part: str) -> str:
    from urllib.parse import quote

    return quote(part, safe="")


MOCK_EVENTS = [
    {
        "event_id": "evt_voice_thought_001",
        "source": "voice",
        "kind": "thought",
        "title": "Turn a voice thought into a ChatAssign UI skeleton",
        "tags": ["thought", "chatassign", "control-plane"],
        "occurred_at": "2026-08-26T05:58:00Z",
        "source_ref": {
            "system": "ChatEvent",
            "event_uri": "chatevent://voice/evt_voice_thought_001",
            "talk_id": "talk_mock_20260826_001",
        },
        "privacy": {
            "content_available": "on_authorized_fetch",
            "default_record_contains_full_transcript": False,
        },
        "excerpt": "A short metadata-only voice thought asking for the first ChatAssign control-plane flow.",
    },
    {
        "event_id": "evt_manual_note_002",
        "source": "manual",
        "kind": "note",
        "title": "Non-matching manual note",
        "tags": ["reference"],
        "occurred_at": "2026-08-26T06:01:00Z",
        "source_ref": {
            "system": "ChatEvent",
            "event_uri": "chatevent://manual/evt_manual_note_002",
        },
        "privacy": {
            "content_available": "metadata_only",
            "default_record_contains_full_transcript": False,
        },
        "excerpt": "This event is present to show the policy filter boundary.",
    },
]


POLICIES = [
    {
        "policy_id": "voice-thought",
        "name": "Voice Thought",
        "rule": "source=voice AND tags contains trigger_alias(thought=[thought,sort])",
        "mode": "confirm-first",
        "available_modes": ["manual", "confirm-first", "supervised-auto", "YOLO"],
        "default_backend_id": "local-chatboard-mock",
        "default_executor": "codex",
        "event_filter_contract": {
            "voice": {"source": "voice", "tag_alias": "thought", "aliases": TRIGGER_TAG_ALIASES["thought"]},
            "zulip_reply": {
                "source": "zulip",
                "filter_owner": "ChatAssign",
                "sender_identity": REX_IDENTITIES,
                "ignore_bot_self": ASSIGNMENT_BOT,
            },
        },
    }
]


BACKENDS = [
    {
        "backend_id": "local-chatboard-mock",
        "name": "Local ChatBoard Mock",
        "kind": "chatboard-backend",
        "base_url": "mock://chatboard/local",
        "status": "mock-ready",
        "capabilities": {
            "workspace_files": True,
            "task_state": True,
            "executor_registry": True,
            "run_lifecycle": True,
            "resume": True,
            "stop": True,
            "collect": True,
            "json_output": True,
        },
        "executors": [
            {"id": "codex", "label": "Codex", "installed": "unknown", "auth": "external", "modes": ["review", "execute"]},
            {"id": "cursor-agent", "label": "Cursor Agent", "installed": "unknown", "auth": "external", "modes": ["execute"]},
            {"id": "opencode", "label": "OpenCode", "installed": "unknown", "auth": "external", "modes": ["execute"]},
        ],
        "real_api_contract": {
            "capabilities": "GET /api/backends/{backend_id}/capabilities",
            "create_task": "POST /api/tasks",
            "start_run": "POST /api/runs",
            "poll_run": "GET /api/runs/{run_id}",
            "collect": "POST /api/runs/{run_id}/collect",
        },
    }
]


def append_timeline(assignment: dict[str, Any], kind: str, title: str, detail: str = "", **extra: Any) -> None:
    assignment.setdefault("timeline", []).append(
        {
            "at": utc_now(),
            "kind": kind,
            "title": title,
            "detail": detail,
            **{key: value for key, value in extra.items() if value is not None},
        }
    )


def transition(assignment: dict[str, Any], new_state: str, detail: str = "") -> None:
    if new_state not in ASSIGNMENT_STATES:
        raise ValueError(f"unsupported state: {new_state}")
    assignment["state"] = new_state
    assignment["status"] = new_state
    append_timeline(assignment, "state", new_state, detail)


def voice_event_matches_policy(event: dict[str, Any], policy: dict[str, Any] | None = None) -> bool:
    tags = {str(tag).lower() for tag in event.get("tags", [])}
    payload_tags = event.get("payload", {}).get("tags", [])
    tags.update(str(tag).lower() for tag in payload_tags if isinstance(payload_tags, list))
    aliases = TRIGGER_TAG_ALIASES["thought"]
    return str(event.get("source")) == "voice" and bool(tags.intersection(aliases))


def zulip_event_from_rex(event: dict[str, Any], assignment: dict[str, Any]) -> bool:
    if str(event.get("source")) != "zulip":
        return False
    sender_email = str(event.get("sender_email") or event.get("payload", {}).get("sender_email") or "")
    sender_id = str(event.get("sender_id") or event.get("payload", {}).get("sender_id") or "")
    sender_name = str(event.get("sender_full_name") or event.get("payload", {}).get("sender_full_name") or "")
    bot_email = ASSIGNMENT_BOT["bot_email"]
    if sender_email and sender_email == bot_email:
        return False
    rex = assignment.get("identity", {}).get("rex") or REX_IDENTITIES
    return sender_email == rex.get("sender_email") or sender_id == rex.get("sender_id") or sender_name == rex.get("display_name")


def is_confirmation_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if not normalized:
        return False
    positive_patterns = [
        r"^(confirmed|approved)\b",
        r"^i\s+(confirm|approve)\b",
        r"^(yes|yep|yeah|ok|okay|sure)\b.*\b(create|start|run|proceed|go ahead|ship)\b",
        r"^(go ahead|ship it|proceed|start|run it|create (the )?task)\b",
    ]
    if any(re.search(pattern, normalized) for pattern in positive_patterns):
        return True
    chinese_markers = ["确认创建", "确认执行", "可以创建", "可以开始", "同意", "接受", "开始吧", "发起吧"]
    return any(marker in text for marker in chinese_markers)


def message_templates(assignment: dict[str, Any]) -> dict[str, str]:
    task_url = assignment.get("links", {}).get("task_url") or assignment.get("route", {}).get("board_task_url") or "-"
    prd_url = assignment.get("links", {}).get("prd_url") or "-"
    assignment_url = assignment.get("links", {}).get("assignment_url") or "-"
    run_url = assignment.get("links", {}).get("run_url") or "-"
    return {
        "initial_summary_questions": (
            f"Assignment draft opened from voice Event `{assignment['source_event']['event_id']}`.\n\n"
            f"Summary: {assignment['review']['proposed_task']['brief']}\n\n"
            "Candidate directions:\n"
            "- Keep ChatEvent metadata-only and policy-neutral.\n"
            "- Let ChatAssign filter voice trigger tags and Zulip Rex replies.\n"
            "- Create ChatBoard Task/PRD only after explicit confirmation.\n\n"
            "Questions: confirm scope, backend target, and whether this should stay a mock run."
        ),
        "draft_refinement": (
            "Draft refined from Rex/demo reply. Current delta: prioritize service-backed ingest contracts, "
            "temporary topic watch lifecycle, and confirmation-gated ChatBoard task creation."
        ),
        "accepted_assigned": (
            "Assignment confirmed and started.\n\n"
            f"- ChatAssign Assignment: {assignment_url}\n"
            f"- ChatBoard Task: {task_url}\n"
            f"- ChatBoard PRD: {prd_url}\n"
            f"- Run: {run_url}"
        ),
        "progress_answer": (
            f"Current state: `{assignment.get('state') or assignment.get('status')}`. "
            f"Run `{assignment.get('run', {}).get('run_id') if assignment.get('run') else 'not-started'}` is tracked on this assignment."
        ),
        "completion_summary": (
            f"Assignment `{assignment['assignment_id']}` completed in ChatAssign service mode. "
            "Artifacts include assignment record, PRD draft, run record, and timeline."
        ),
    }


def chatevent_watch_contract(assignment: dict[str, Any], state: str = "active") -> dict[str, Any]:
    topic = assignment["zulip_thread"]["topic"]
    interval = 10 if assignment["state"] in {"waiting_for_user", "waiting_for_confirmation", "running"} else 60
    ttl = 1800 if assignment["state"] in TERMINALISH_STATES else 900
    return {
        "watch_id": assignment["watch"]["watch_id"],
        "source": "zulip",
        "target": {"stream": "voice note", "topic": topic},
        "assignment_id": assignment["assignment_id"],
        "interval_seconds": interval,
        "ttl_seconds": ttl,
        "state": state,
        "owner": "ChatAssign",
        "filter_boundary": "ChatEvent watches only stream/topic; Rex/demo sender filtering is done by ChatAssign Event consumption.",
        "api_contract": {
            "request": "POST /api/watches",
            "update": "PATCH /api/watches/{watch_id}",
            "close": "POST /api/watches/{watch_id}/close",
        },
    }


class Store:
    def __init__(self, home: Path):
        self.home = home
        self.assignments_dir = home / "assignments"
        self.projects_dir = home / "projects"
        self.runs_dir = home / "runs"
        self.policies_dir = home / "policies"
        self.backends_dir = home / "backends"
        self.logs_dir = home / "logs"
        self.db_path = home / "state.db"
        self.resolver = LocalPublicResolver(load_resolver_config(home))
        self.ensure()

    def ensure(self) -> None:
        for path in [
            self.assignments_dir,
            self.projects_dir,
            self.runs_dir,
            self.policies_dir,
            self.backends_dir,
            self.logs_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    assignment_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()}
            if "data" not in columns and "payload" in columns:
                conn.execute("ALTER TABLE assignments ADD COLUMN data TEXT")
                conn.execute("UPDATE assignments SET data = payload WHERE data IS NULL")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()}
            if "data" not in columns:
                raise RuntimeError("assignments table is missing required data column")
        self.seed_config_files()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def seed_config_files(self) -> None:
        policy_path = self.policies_dir / "voice-thought.json"
        if not policy_path.exists():
            policy_path.write_text(json.dumps(POLICIES[0], indent=2) + "\n", encoding="utf-8")
        backend_path = self.backends_dir / "local-chatboard-mock.json"
        if not backend_path.exists():
            backend_path.write_text(json.dumps(BACKENDS[0], indent=2) + "\n", encoding="utf-8")
        resolver_path = self.home / "resolver.example.json"
        if not resolver_path.exists():
            resolver_path.write_text(
                json.dumps(
                    {
                        "local_root": str(self.home),
                        "public_base_url": "https://example.invalid/chatassign",
                        "description": "Copy to resolver.json or set CHATASSIGN_PUBLIC_BASE_URL to enable public path resolution.",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    def list_assignments(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT data FROM assignments ORDER BY updated_at DESC").fetchall()
        return [json.loads(row["data"]) for row in rows]

    def get_assignment(self, assignment_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT data FROM assignments WHERE assignment_id = ?", (assignment_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def save_assignment(self, assignment: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        assignment.setdefault("created_at", now)
        assignment["updated_at"] = now
        self._write_artifacts(assignment)
        data = json.dumps(assignment, sort_keys=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO assignments (assignment_id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(assignment_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
                """,
                (assignment["assignment_id"], data, assignment["created_at"], assignment["updated_at"]),
            )
        return assignment

    def _write_artifacts(self, assignment: dict[str, Any]) -> None:
        project_id = assignment["assign_project_id"]
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "runs").mkdir(exist_ok=True)
        (project_dir / "assignment.json").write_text(json.dumps(assignment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (self.assignments_dir / f"{assignment['assignment_id']}.json").write_text(
            json.dumps(assignment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        review = assignment.get("review", {})
        (project_dir / "review.md").write_text(render_review_md(assignment, review), encoding="utf-8")
        (project_dir / "PRD.md").write_text(render_prd_md(assignment), encoding="utf-8")
        (project_dir / "prompt.md").write_text(render_prompt_md(assignment), encoding="utf-8")
        (project_dir / "progress.md").write_text(f"# Progress\n\n- {assignment['updated_at']}: {assignment['status']}\n", encoding="utf-8")
        if assignment.get("run"):
            run = assignment["run"]
            run_path = self.runs_dir / f"{run['run_id']}.json"
            run_path.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (project_dir / "runs" / f"{run['run_id']}.json").write_text(
                json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    def path_bundle(self, assignment: dict[str, Any]) -> dict[str, Any]:
        project_dir = self.projects_dir / assignment["assign_project_id"]
        report_path = project_dir / "result.md"
        paths = {
            "assign_project_path": str(project_dir),
            "assignment_record_path": str(self.assignments_dir / f"{assignment['assignment_id']}.json"),
            "prompt_path": str(project_dir / "prompt.md"),
            "report_path": str(report_path),
        }
        urls = {key.replace("_path", "_url"): self.resolver.resolve(value) for key, value in paths.items()}
        return {"local": paths, "public": urls}


def render_review(event: dict[str, Any], policy_id: str) -> dict[str, Any]:
    matched = voice_event_matches_policy(event)
    return {
        "review_id": f"rev_{uuid.uuid4().hex[:10]}",
        "policy_id": policy_id,
        "actionable": matched,
        "reason": "Matches source=voice and thought trigger alias policy." if matched else "Does not match the default voice-thought policy.",
        "proposed_task": {
            "title": event.get("title", "Untitled assignment"),
            "brief": "Create a ChatAssign control-plane task from the event metadata without storing private transcript content.",
            "acceptance": [
                "Event provenance is retained.",
                "Policy, backend route, task record, run/session refs, and status are tracked.",
                "Mock adapter can be replaced by ChatBoard executor API calls.",
            ],
        },
        "risks": [
            "Private source content must remain behind explicit authorization.",
            "Real ChatBoard backend contract may evolve while this mock is in place.",
        ],
        "questions": [
            "Should this be confirmed by the user before dispatch?",
            "Which ChatBoard backend should own the task workspace?",
        ],
        "created_at": utc_now(),
    }


def render_review_md(assignment: dict[str, Any], review: dict[str, Any]) -> str:
    return (
        f"# Review: {assignment['title']}\n\n"
        f"- Assignment: `{assignment['assignment_id']}`\n"
        f"- Source event: `{assignment['source_event']['event_id']}`\n"
        f"- Policy: `{assignment['policy_id']}`\n"
        f"- Actionable: `{review.get('actionable')}`\n\n"
        f"## Proposed Task\n\n{review.get('proposed_task', {}).get('brief', 'Pending review.')}\n"
    )


def render_prd_md(assignment: dict[str, Any]) -> str:
    acceptance = assignment.get("review", {}).get("proposed_task", {}).get("acceptance", [])
    lines = "\n".join(f"- {item}" for item in acceptance) or "- Pending acceptance criteria."
    return f"# PRD: {assignment['title']}\n\n## Acceptance\n\n{lines}\n"


def render_prompt_md(assignment: dict[str, Any]) -> str:
    return (
        f"# Worker Prompt\n\n"
        f"Assignment `{assignment['assignment_id']}` was created from `{assignment['source_event']['event_id']}`.\n"
        "Use source metadata and explicit user instructions only. Do not request or store full voice transcripts by default.\n"
    )


def _event_from_payload(payload: dict[str, Any], event_id: str) -> dict[str, Any]:
    supplied = payload.get("event")
    if isinstance(supplied, dict):
        tags = supplied.get("tags") or supplied.get("payload", {}).get("tags") or []
        if not isinstance(tags, list):
            tags = []
        source_ref = supplied.get("source_ref") or {
            "system": "ChatEvent",
            "event_uri": f"chatevent://{supplied.get('source', 'unknown')}/{event_id}",
            "talk_id": supplied.get("payload", {}).get("talk_id") or supplied.get("target", {}).get("key"),
        }
        return {
            "event_id": str(supplied.get("event_id") or supplied.get("id") or event_id),
            "source": str(supplied.get("source") or ""),
            "kind": str(supplied.get("kind") or ""),
            "title": str(supplied.get("title") or supplied.get("payload", {}).get("title") or "Untitled assignment"),
            "tags": [str(tag) for tag in tags],
            "occurred_at": str(supplied.get("occurred_at") or supplied.get("payload", {}).get("updated_at") or utc_now()),
            "source_ref": source_ref,
            "privacy": {
                "content_available": "metadata_only",
                "default_record_contains_full_transcript": False,
            },
        }
    return next((item for item in MOCK_EVENTS if item["event_id"] == event_id), MOCK_EVENTS[0])


def create_assignment(store: Store, payload: dict[str, Any]) -> dict[str, Any]:
    event_id = payload.get("event_id") or "evt_voice_thought_001"
    event = _event_from_payload(payload, event_id)
    policy_id = payload.get("policy_id") or "voice-thought"
    assignment_id = f"asg_{uuid.uuid4().hex[:10]}"
    project_id = f"cap_{assignment_id[4:]}"
    review = render_review(event, policy_id)
    topic = payload.get("zulip_topic") or f"voice note: {event.get('source_ref', {}).get('talk_id') or event['event_id']}"
    watch_id = f"watch_{uuid.uuid4().hex[:10]}"
    assignment = {
        "assignment_id": assignment_id,
        "assign_project_id": project_id,
        "title": event["title"],
        "state": "voice_seen",
        "status": "voice_seen",
        "policy_id": policy_id,
        "source_event": {
            "event_id": event["event_id"],
            "source": event["source"],
            "kind": event["kind"],
            "tags": event["tags"],
            "occurred_at": event["occurred_at"],
            "source_ref": event["source_ref"],
        },
        "privacy": {
            "stored_full_transcript": False,
            "stored_full_summary": False,
            "content_policy": "metadata-only by default; fetch private content only through authorized adapter flow",
        },
        "review": review,
        "draft": {
            "version": 1,
            "summary": review["proposed_task"]["brief"],
            "questions": review["questions"],
            "last_user_reply_event_id": None,
            "confirmation_required": True,
        },
        "zulip_thread": {
            "stream": "voice note",
            "topic": topic,
            "message_ids": [],
            "bot_identity": ASSIGNMENT_BOT,
            "status": "opened",
            "thread_url": f"mock://zulip/voice-note/{quote_path_part(topic)}",
        },
        "watch": {
            "watch_id": watch_id,
            "state": "active",
            "interval_seconds": 10,
            "ttl_seconds": 900,
            "last_cursor": None,
            "contract": "POST /api/watches source=zulip target={stream,topic} ttl_seconds interval_seconds assignment_id",
        },
        "identity": {
            "rex": REX_IDENTITIES,
            "assignment_bot": ASSIGNMENT_BOT,
            "sender_filter_owner": "ChatAssign",
        },
        "route": {
            "backend_id": payload.get("backend_id") or "local-chatboard-mock",
            "executor": payload.get("executor") or "codex",
            "backend_base_url": payload.get("backend_base_url"),
            "board_root": payload.get("board_root"),
            "mode": payload.get("mode") or "mock",
            "board_project_id": None,
            "board_task_id": None,
            "board_task_url": None,
            "prd_url": None,
        },
        "run": None,
        "links": {
            "assignment_url": f"mock://chatassign/assignments/{assignment_id}",
            "thread_url": f"mock://zulip/voice-note/{quote_path_part(topic)}",
            "task_url": None,
            "prd_url": None,
            "run_url": None,
        },
        "contracts": {
            "event_ingest": {
                "voice_filter": "ChatAssign consumes ChatEvent records where source=voice and tags intersect trigger aliases [thought, sort].",
                "zulip_reply_filter": "ChatAssign consumes source=zulip records for this stream/topic and filters Rex/demo sender identity itself.",
                "endpoint": "POST /api/events/ingest",
            },
            "chatevent_watch": {
                "request": "POST /api/watches source=zulip target={stream:'voice note',topic} interval_seconds ttl_seconds assignment_id",
                "update": "PATCH /api/watches/{watch_id}",
                "close": "POST /api/watches/{watch_id}/close",
            },
            "chatboard": BACKENDS[0]["real_api_contract"],
        },
        "decision": {
            "mode": payload.get("mode") or "confirm-first",
            "human_decision": "pending",
            "decided_at": None,
        },
        "timestamps": {
            "created_at": utc_now(),
            "accepted_at": None,
            "dispatched_at": None,
            "completed_at": None,
        },
        "timeline": [],
        "bot_messages": {},
    }
    transition(assignment, "voice_seen", "Matched voice Event and assignment trigger alias policy.")
    transition(assignment, "draft_opened", "Opened Assignment Bot Zulip thread in mock channel.")
    templates = message_templates(assignment)
    initial_id = f"zulip_msg_{uuid.uuid4().hex[:8]}"
    assignment["zulip_thread"]["message_ids"].append(initial_id)
    assignment["bot_messages"]["initial_summary_questions"] = templates["initial_summary_questions"]
    append_timeline(assignment, "bot_message", "initial_summary_questions", templates["initial_summary_questions"], message_id=initial_id)
    transition(assignment, "waiting_for_user", "Waiting for Rex/demo clarification reply before creating ChatBoard task.")
    assignment["watch"] = chatevent_watch_contract(assignment, "active")
    assignment["paths"] = store.path_bundle(assignment)
    return store.save_assignment(assignment)


def route_assignment(store: Store, assignment: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    assignment["route"].update(
        {
            "backend_id": payload.get("backend_id") or assignment["route"]["backend_id"],
            "executor": payload.get("executor") or assignment["route"]["executor"],
            "backend_base_url": payload.get("backend_base_url") or assignment["route"].get("backend_base_url"),
            "board_root": payload.get("board_root") or assignment["route"].get("board_root"),
            "mode": payload.get("mode") or assignment["route"].get("mode") or "mock",
        }
    )
    assignment["paths"] = store.path_bundle(assignment)
    return store.save_assignment(assignment)


def refine_from_reply(store: Store, assignment: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("content") or payload.get("text") or payload.get("message") or "")
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    event_id = str(event.get("event_id") or payload.get("event_id") or f"evt_zulip_reply_{uuid.uuid4().hex[:8]}")
    sender = {
        "sender_email": event.get("sender_email") or payload.get("sender_email") or REX_IDENTITIES["sender_email"],
        "sender_id": event.get("sender_id") or payload.get("sender_id") or REX_IDENTITIES["sender_id"],
        "sender_full_name": event.get("sender_full_name") or payload.get("sender_full_name") or REX_IDENTITIES["display_name"],
    }
    synthetic_event = {"source": "zulip", "event_id": event_id, "payload": sender, **sender}
    if not zulip_event_from_rex(synthetic_event, assignment):
        append_timeline(assignment, "ignored_event", "zulip_sender_filtered", "Zulip Event did not match Rex/demo identity.", event_id=event_id)
        return store.save_assignment(assignment)
    if assignment.get("state") in {"running", "needs_review", "completed", "blocked", "followup_monitoring"}:
        return answer_progress(store, assignment, payload)
    if is_confirmation_text(text):
        append_timeline(assignment, "user_reply", "confirmation_reply", text or "Explicit confirmation.", event_id=event_id)
        return confirm_assignment(store, assignment, payload)
    transition(assignment, "refining_from_user_reply", f"Consumed Rex/demo Zulip Event `{event_id}`.")
    assignment["draft"]["version"] = int(assignment["draft"].get("version") or 1) + 1
    assignment["draft"]["last_user_reply_event_id"] = event_id
    assignment["draft"]["summary"] = (
        "Service-backed assignment loop: voice trigger Event, Assignment Bot thread, Rex/demo reply refinement, "
        "confirmation-gated ChatBoard Task/PRD/run, and same-thread progress updates."
    )
    templates = message_templates(assignment)
    assignment["bot_messages"]["draft_refinement"] = templates["draft_refinement"]
    msg_id = f"zulip_msg_{uuid.uuid4().hex[:8]}"
    assignment["zulip_thread"]["message_ids"].append(msg_id)
    append_timeline(assignment, "user_reply", "rex_demo_reply", text, event_id=event_id)
    append_timeline(assignment, "bot_message", "draft_refinement", templates["draft_refinement"], message_id=msg_id)
    transition(assignment, "waiting_for_confirmation", "Draft refined; waiting for explicit Rex/demo confirmation.")
    assignment["watch"] = chatevent_watch_contract(assignment, "active")
    assignment["paths"] = store.path_bundle(assignment)
    return store.save_assignment(assignment)


def confirm_assignment(store: Store, assignment: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    now = utc_now()
    transition(assignment, "confirmed", "Explicit user confirmation received.")
    assignment["decision"]["human_decision"] = "accepted"
    assignment["decision"]["decided_at"] = assignment["decision"]["decided_at"] or now
    assignment["timestamps"]["accepted_at"] = assignment["timestamps"]["accepted_at"] or now
    assignment = dispatch_assignment(store, assignment, from_confirmation=True)
    templates = message_templates(assignment)
    assignment["bot_messages"]["accepted_assigned"] = templates["accepted_assigned"]
    msg_id = f"zulip_msg_{uuid.uuid4().hex[:8]}"
    assignment["zulip_thread"]["message_ids"].append(msg_id)
    append_timeline(assignment, "bot_message", "accepted_assigned", templates["accepted_assigned"], message_id=msg_id)
    return store.save_assignment(assignment)


def answer_progress(store: Store, assignment: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("content") or payload.get("text") or payload.get("message") or "Progress requested.")
    append_timeline(assignment, "user_reply", "progress_question", text, event_id=payload.get("event_id"))
    templates = message_templates(assignment)
    assignment["bot_messages"]["progress_answer"] = templates["progress_answer"]
    msg_id = f"zulip_msg_{uuid.uuid4().hex[:8]}"
    assignment["zulip_thread"]["message_ids"].append(msg_id)
    append_timeline(assignment, "bot_message", "progress_answer", templates["progress_answer"], message_id=msg_id)
    assignment["watch"] = chatevent_watch_contract(assignment, "active")
    return store.save_assignment(assignment)


def complete_assignment(store: Store, assignment: dict[str, Any], status: str = "completed") -> dict[str, Any]:
    transition(assignment, status, f"Run moved to {status}.")
    if assignment.get("run"):
        assignment["run"]["status"] = status
        assignment["run"]["updated_at"] = utc_now()
    if status == "completed":
        assignment["timestamps"]["completed_at"] = utc_now()
        templates = message_templates(assignment)
        assignment["bot_messages"]["completion_summary"] = templates["completion_summary"]
        msg_id = f"zulip_msg_{uuid.uuid4().hex[:8]}"
        assignment["zulip_thread"]["message_ids"].append(msg_id)
        append_timeline(assignment, "bot_message", "completion_summary", templates["completion_summary"], message_id=msg_id)
        transition(assignment, "followup_monitoring", "Keeping topic watch alive at decayed interval for progress follow-ups.")
    assignment["watch"] = chatevent_watch_contract(assignment, "decayed" if status == "completed" else "active")
    assignment["paths"] = store.path_bundle(assignment)
    return store.save_assignment(assignment)


def _http_json(
    base_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    api_token: str | None = None,
    executor_token: str | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    method = "GET" if payload is None else "POST"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_token:
        headers["X-ChatBoard-Token"] = api_token
    if executor_token:
        headers["X-ChatBoard-Executor-Token"] = executor_token
    request = urllib_request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(request, timeout=20) as response:  # noqa: S310 - route config is server-side.
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ChatBoard HTTP {exc.code}: {body}") from exc


def _dispatch_to_chatboard_http(assignment: dict[str, Any], paths: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    route = assignment["route"]
    base_url = str(route.get("backend_base_url") or "").strip()
    if not base_url:
        return {}, {}
    root = route.get("board_root")
    root_query = f"?root={urllib_parse.quote(str(root), safe='')}" if root else ""
    task_payload = {
        "title": assignment["title"],
        "description": "ChatAssign voice-thought pilot task created from metadata-only ChatEvent payload.",
        "topic": "chatarch",
        "slug": f"08-26-voice-thought-{assignment['assignment_id']}",
        "source_platform": "chatevent",
        "source_url": assignment["source_event"]["source_ref"].get("event_uri"),
        "accept_mode": "auto",
        "side_effect_level": "mock",
        "next_action": "Run bounded mock executor and collect result.",
        "assignee": route.get("executor") or "codex",
        "tags": ["voice", "thought", "chatassign", "e2e"],
    }
    api_token = os.environ.get("CHATASSIGN_CHATBOARD_API_TOKEN")
    executor_token = os.environ.get("CHATASSIGN_CHATBOARD_EXECUTOR_TOKEN")
    task_response = _http_json(base_url, f"/api/tasks{root_query}", task_payload, api_token=api_token)
    card = task_response.get("card") or {}
    if isinstance(card, dict):
        if isinstance(task_response.get("task_link"), dict):
            card["task_link"] = task_response["task_link"]
        if isinstance(task_response.get("prd_link"), dict):
            card["prd_link"] = task_response["prd_link"]
    task_id = card.get("id")
    run_payload = {
        "executor": route.get("executor") or "codex",
        "task_id": task_id,
        "project_id": task_id,
        "mode": route.get("mode") or "mock",
        "workdir": paths["local"]["assign_project_path"],
        "prompt_path": paths["local"]["prompt_path"],
        "report_path": paths["local"]["report_path"],
    }
    run_response = _http_json(
        base_url,
        f"/api/runs{root_query}",
        run_payload,
        api_token=api_token,
        executor_token=executor_token if run_payload["mode"] == "real" else None,
    )
    run = run_response.get("run") or {}
    collect = {}
    if executor_token and run.get("run_id") and run.get("status") in {"done", "failed", "stopped"}:
        collect = _http_json(
            base_url,
            f"/api/runs/{urllib_parse.quote(run['run_id'], safe='')}/collect{root_query}",
            {},
            api_token=api_token,
            executor_token=executor_token,
        )
    return card, collect.get("run") or run


def dispatch_assignment(store: Store, assignment: dict[str, Any], *, from_confirmation: bool = False) -> dict[str, Any]:
    now = utc_now()
    if not from_confirmation and assignment.get("state") not in {"confirmed", "board_task_created", "running"}:
        raise ValueError("ChatBoard task creation requires explicit confirmation first")
    if assignment["decision"].get("human_decision") != "accepted":
        assignment["decision"]["human_decision"] = "accepted"
        assignment["decision"]["decided_at"] = assignment["decision"]["decided_at"] or now
        assignment["timestamps"]["accepted_at"] = assignment["timestamps"]["accepted_at"] or now
    assignment["timestamps"]["dispatched_at"] = now
    board_task_id = f"task_{uuid.uuid4().hex[:8]}"
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    assignment["route"].update(
        {
            "board_project_id": f"boardproj_{assignment['assign_project_id']}",
            "board_task_id": board_task_id,
            "board_task_url": f"mock://chatboard/local/tasks/{board_task_id}",
            "prd_url": f"mock://chatboard/local/tasks/{board_task_id}/files/PRD.md",
        }
    )
    transition(assignment, "board_task_created", "ChatBoard Task and PRD links created after confirmation.")
    paths = store.path_bundle(assignment)
    run = {
        "run_id": run_id,
        "assignment_id": assignment["assignment_id"],
        "backend": assignment["route"]["backend_id"],
        "executor": assignment["route"]["executor"],
        "backend_session_id": f"mock_session_{uuid.uuid4().hex[:10]}",
        "process": {
            "host": os.uname().nodename,
            "pid": None,
            "process_session_id": None,
            "status": "running",
        },
        "workspace": {
            "chatassign_home": str(store.home),
            "assign_project_path": paths["local"]["assign_project_path"],
            "external_playground_project_path": None,
            "workdir": paths["local"]["assign_project_path"],
        },
        "prompt_path": paths["local"]["prompt_path"],
        "prompt_url": paths["public"]["prompt_url"],
        "report_path": paths["local"]["report_path"],
        "report_url": paths["public"]["report_url"],
        "created_at": now,
        "updated_at": now,
        "resume_command_hint": "Use the selected ChatBoard backend resume endpoint with this backend_session_id.",
        "status": "running",
        "adapter_contract": "mock ChatBoard adapter: create_task -> start_run -> poll_run -> collect",
    }
    assignment["run"] = run
    assignment["paths"] = paths
    assignment["links"].update(
        {
            "assignment_url": assignment["paths"]["public"].get("assignment_record_url") or assignment["links"]["assignment_url"],
            "task_url": assignment["route"]["board_task_url"],
            "prd_url": assignment["route"]["prd_url"],
            "run_url": f"mock://chatboard/local/runs/{run_id}",
        }
    )
    try:
        card, board_run = _dispatch_to_chatboard_http(assignment, paths)
    except Exception as exc:
        run["status"] = "blocked"
        run["http_error"] = str(exc)
    else:
        if board_run:
            task_link = card.get("task_link") if isinstance(card.get("task_link"), dict) else {}
            prd_link = card.get("prd_link") if isinstance(card.get("prd_link"), dict) else {}
            assignment["route"].update(
                {
                    "board_project_id": card.get("id") or assignment["route"]["board_project_id"],
                    "board_task_id": card.get("id") or assignment["route"]["board_task_id"],
                    "board_task_url": task_link.get("public_url") or assignment["route"]["board_task_url"],
                    "prd_url": prd_link.get("public_url") or assignment["route"].get("prd_url"),
                }
            )
            run.update(
                {
                    "run_id": board_run.get("run_id") or run["run_id"],
                    "backend": "chatboard-http",
                    "backend_session_id": board_run.get("backend_session_id"),
                    "process": {
                        "host": os.uname().nodename,
                        "pid": board_run.get("os_pid"),
                        "process_session_id": board_run.get("process_session_id"),
                        "status": board_run.get("status"),
                    },
                    "workspace": {
                        **run["workspace"],
                        "external_playground_project_path": assignment["route"].get("board_root"),
                        "workdir": board_run.get("workdir") or run["workspace"]["workdir"],
                    },
                    "prompt_path": board_run.get("prompt_path") or run["prompt_path"],
                    "report_path": board_run.get("report_path") or run["report_path"],
                    "created_at": board_run.get("created_at") or run["created_at"],
                    "updated_at": board_run.get("updated_at") or utc_now(),
                    "status": board_run.get("status") or run["status"],
                    "adapter_contract": "ChatBoard HTTP: POST /api/tasks -> POST /api/runs -> POST /api/runs/{run_id}/collect",
                    "public_links": board_run.get("public_links") or {},
                }
            )
            public_links = board_run.get("public_links") or {}
            run_link = public_links.get("run") if isinstance(public_links.get("run"), dict) else {}
            report_link = public_links.get("report") if isinstance(public_links.get("report"), dict) else {}
            assignment["links"].update(
                {
                    "task_url": assignment["route"]["board_task_url"],
                    "prd_url": assignment["route"].get("prd_url") or assignment["links"]["prd_url"],
                    "run_url": run_link.get("public_url") or report_link.get("public_url") or assignment["links"]["run_url"],
                }
            )
    run_mode = assignment["route"].get("mode") or "mock"
    transition(assignment, "running", f"Started bounded {run_mode} run through ChatBoard contract.")
    assignment["watch"] = chatevent_watch_contract(assignment, "active")
    if run_mode != "real":
        result_path = Path(paths["local"]["report_path"])
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            f"# Mock Result\n\nAssignment `{assignment['assignment_id']}` dispatched to mock ChatBoard backend.\n",
            encoding="utf-8",
        )
    return store.save_assignment(assignment)


class Handler(SimpleHTTPRequestHandler):
    store: Store

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean = posixpath.normpath(unquote(parsed.path))
        if clean == "/":
            return str(STATIC_DIR / "index.html")
        return str(STATIC_DIR / clean.lstrip("/"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            self.handle_api_get(path, parse_qs(parsed.query))
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = safe_json_loads(raw, {})
        self.handle_api_post(parsed.path, payload)

    def handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/health":
            self.json_response(
                {
                    "ok": True,
                    "service": "chatassign",
                    "time": utc_now(),
                    "chatassign_home": str(self.store.home),
                    "resolver": self.store.resolver.status(),
                    "integrations": integrations(self.store),
                }
            )
            return
        if path == "/api/events/candidates":
            self.json_response({"events": MOCK_EVENTS})
            return
        if path == "/api/policies":
            self.json_response({"policies": POLICIES})
            return
        if path == "/api/backends":
            self.json_response({"backends": BACKENDS})
            return
        if path == "/api/contracts":
            self.json_response(contracts())
            return
        if path == "/api/assignments":
            self.json_response({"assignments": self.store.list_assignments()})
            return
        if path == "/api/integrations":
            self.json_response(integrations(self.store))
            return
        if path.startswith("/api/assignments/"):
            assignment_id = path.rsplit("/", 1)[-1]
            assignment = self.store.get_assignment(assignment_id)
            if assignment:
                self.json_response(assignment)
            else:
                self.json_response({"error": "assignment not found"}, HTTPStatus.NOT_FOUND)
            return
        self.json_response({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def handle_api_post(self, path: str, payload: dict[str, Any]) -> None:
        if path == "/api/events/ingest":
            self.json_response(ingest_event(self.store, payload), HTTPStatus.CREATED)
            return
        if path == "/api/assignments":
            self.json_response(create_assignment(self.store, payload), HTTPStatus.CREATED)
            return
        if path.startswith("/api/assignments/"):
            parts = [part for part in path.split("/") if part]
            if len(parts) != 4:
                self.json_response({"error": "invalid assignment endpoint"}, HTTPStatus.NOT_FOUND)
                return
            assignment_id, action = parts[2], parts[3]
            assignment = self.store.get_assignment(assignment_id)
            if not assignment:
                self.json_response({"error": "assignment not found"}, HTTPStatus.NOT_FOUND)
                return
            if action == "review":
                event = next((item for item in MOCK_EVENTS if item["event_id"] == assignment["source_event"]["event_id"]), MOCK_EVENTS[0])
                assignment["review"] = render_review(event, assignment["policy_id"])
            elif action == "route":
                assignment = route_assignment(self.store, assignment, payload)
                self.json_response(assignment)
                return
            elif action == "dispatch":
                try:
                    assignment = dispatch_assignment(self.store, assignment)
                except ValueError as exc:
                    self.json_response({"error": str(exc)}, HTTPStatus.CONFLICT)
                    return
                self.json_response(assignment)
                return
            elif action == "reply":
                assignment = refine_from_reply(self.store, assignment, payload)
                self.json_response(assignment)
                return
            elif action == "confirm":
                assignment = confirm_assignment(self.store, assignment, payload)
                self.json_response(assignment)
                return
            elif action == "progress":
                assignment = answer_progress(self.store, assignment, payload)
                self.json_response(assignment)
                return
            elif action == "complete":
                status = payload.get("status") or "completed"
                if status not in {"completed", "needs_review", "blocked"}:
                    self.json_response({"error": "status must be completed, needs_review, or blocked"}, HTTPStatus.BAD_REQUEST)
                    return
                assignment = complete_assignment(self.store, assignment, status)
                self.json_response(assignment)
                return
            elif action == "status":
                status = payload.get("status")
                if status not in STATUSES:
                    self.json_response({"error": f"status must be one of {sorted(STATUSES)}"}, HTTPStatus.BAD_REQUEST)
                    return
                if status == "done":
                    assignment = complete_assignment(self.store, assignment, "completed")
                    self.json_response(assignment)
                    return
                assignment["status"] = status
                assignment["state"] = "completed" if status == "done" else status
                if assignment.get("run"):
                    assignment["run"]["status"] = "completed" if status == "done" else status
                    assignment["run"]["updated_at"] = utc_now()
                append_timeline(assignment, "state", assignment["state"], "Legacy status endpoint updated state.")
            else:
                self.json_response({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            assignment["paths"] = self.store.path_bundle(assignment)
            self.json_response(self.store.save_assignment(assignment))
            return
        self.json_response({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def json_response(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def ingest_event(store: Store, payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    if voice_event_matches_policy(event):
        assignment = create_assignment(store, {"event": event, "policy_id": payload.get("policy_id") or "voice-thought"})
        return {"accepted": True, "action": "assignment_created", "assignment": assignment}
    if str(event.get("source")) == "zulip":
        assignment_id = event.get("assignment_id") or event.get("payload", {}).get("assignment_id") or payload.get("assignment_id")
        assignment = store.get_assignment(str(assignment_id)) if assignment_id else None
        if assignment and zulip_event_from_rex(event, assignment):
            updated = refine_from_reply(store, assignment, {"event": event, "content": event.get("content") or event.get("payload", {}).get("content")})
            return {"accepted": True, "action": "assignment_refined", "assignment": updated}
        return {"accepted": False, "action": "ignored_zulip_event", "reason": "No assignment id or Rex/demo sender identity match."}
    return {"accepted": False, "action": "ignored_event", "reason": "No ChatAssign policy matched."}


def contracts() -> dict[str, Any]:
    return {
        "state_machine": {
            "states": ASSIGNMENT_STATES,
            "flow": "voice_seen -> draft_opened -> waiting_for_user -> refining_from_user_reply -> waiting_for_confirmation -> confirmed -> board_task_created -> running -> needs_review|completed|blocked -> followup_monitoring",
            "confirmation_gate": "ChatBoard create_task/start_run is rejected until explicit confirmation.",
        },
        "event_consumer": {
            "voice_filter": {"source": "voice", "trigger_tag_aliases": TRIGGER_TAG_ALIASES},
            "zulip_filter": {
                "source": "zulip",
                "scope": "assignment stream/topic watch records",
                "sender_identity": REX_IDENTITIES,
                "bot_identity": ASSIGNMENT_BOT,
                "owner": "ChatAssign, not ChatEvent capture",
            },
            "endpoint": "POST /api/events/ingest",
        },
        "chatevent_watch_client": {
            "request": {
                "method": "POST",
                "path": "/api/watches",
                "json": {
                    "source": "zulip",
                    "target": {"stream": "voice note", "topic": "<assignment topic>"},
                    "interval_seconds": 10,
                    "ttl_seconds": 900,
                    "assignment_id": "<assignment id>",
                },
            },
            "update": "PATCH /api/watches/{watch_id} interval_seconds ttl_seconds state",
            "close": "POST /api/watches/{watch_id}/close",
            "decay": "After completed/blocked/needs_review, interval becomes 60s and ttl 1800s.",
        },
        "chatboard_http_client": {
            "create_task": "POST /api/tasks?root=<optional-board-root>",
            "start_run": "POST /api/runs?root=<optional-board-root>",
            "poll_run": "GET /api/runs/{run_id}?root=<optional-board-root>",
            "collect": "POST /api/runs/{run_id}/collect?root=<optional-board-root>",
            "links_expected": ["task_url", "prd_url", "run_url", "report_url"],
            "safety": "Prototype defaults to mock/safe run and only calls ChatBoard after confirmation.",
        },
        "bot_templates": [
            "initial_summary_questions",
            "draft_refinement",
            "accepted_assigned",
            "progress_answer",
            "completion_summary",
        ],
    }


def integrations(store: Store) -> dict[str, Any]:
    return {
        "chatevent": {
            "status": "mock",
            "profile": os.environ.get("CHATASSIGN_EVENT_PROFILE", "mock-chatevent"),
            "candidate_source": "in-memory metadata-only sample events",
            "consumer_contract": contracts()["event_consumer"],
            "temporary_watch_contract": contracts()["chatevent_watch_client"],
        },
        "chatboard": {
            "status": "mock",
            "profile": os.environ.get("CHATASSIGN_BOARD_PROFILE", "mock-chatboard"),
            "adapter": "MockChatBoardBackendAdapter",
            "swappable_contract": contracts()["chatboard_http_client"],
        },
        "user_channel": {
            "status": "profile-reference-only",
            "profile": os.environ.get("CHATASSIGN_USER_CHANNEL_PROFILE", "mock-user-channel"),
            "core_hardcodes_zulip": False,
        },
        "resolver": store.resolver.status(),
        "config_surface": {
            "CHATASSIGN_BASE_URL": "service URL",
            "CHATASSIGN_API_KEY": "sensitive",
            "CHATASSIGN_HOME": "default data root override",
            "CHATASSIGN_MODEL_PROVIDER": "reviewer provider",
            "CHATASSIGN_MODEL": "reviewer model",
            "CHATASSIGN_MODEL_BASE_URL": "optional model endpoint",
            "CHATASSIGN_MODEL_API_KEY": "sensitive",
            "CHATASSIGN_EVENT_PROFILE": "ChatEvent profile reference",
            "CHATASSIGN_BOARD_PROFILE": "ChatBoard backend profile reference",
            "CHATASSIGN_USER_CHANNEL_PROFILE": "user-channel adapter profile reference",
            "CHATASSIGN_DEFAULT_POLICY": "default policy id",
            "CHATASSIGN_DEFAULT_BACKEND": "default backend id",
            "CHATASSIGN_PUBLIC_LOCAL_ROOT": "local root for shareable-link resolver",
            "CHATASSIGN_PUBLIC_BASE_URL": "public URL prefix for resolved paths",
            "CHATASSIGN_RESOLVER_CONFIG": "optional resolver JSON path",
        },
    }


def build_server(host: str, port: int, home: Path | None = None) -> ThreadingHTTPServer:
    store = Store(home or chatassign_home())
    Handler.store = store
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ChatAssign HTTP service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--home", default=None, help="Override ChatAssign data root for this process.")
    args = parser.parse_args()
    server = build_server(args.host, args.port, Path(args.home).expanduser() if args.home else None)
    print(f"ChatAssign serving http://{args.host}:{args.port}")
    print(f"Data root: {Handler.store.home}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
