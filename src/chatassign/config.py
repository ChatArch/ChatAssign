"Typed environment configuration for ChatAssign."

from chatenv import BaseEnvConfig, EnvField


class ChatassignConfig(BaseEnvConfig):
    "ChatAssign ChatEnv configuration."

    _title = "ChatAssign Configuration"
    _aliases = ["chatassign"]
    _storage_dir = "ChatAssign"

    @classmethod
    def test(cls) -> None:
        """Validate schema registration without external side effects."""

        print(f"Testing {cls._title}...")
        print("Schema loaded; no network test is required.")

    CHATASSIGN_API_KEY = EnvField(
        "CHATASSIGN_API_KEY",
        desc="API key for ChatAssign HTTP API",
        is_sensitive=True,
    )

    CHATASSIGN_HOME = EnvField("CHATASSIGN_HOME", desc="ChatAssign data root")
    CHATASSIGN_BASE_URL = EnvField("CHATASSIGN_BASE_URL", desc="ChatAssign public/service URL")
    CHATASSIGN_EVENT_PROFILE = EnvField("CHATASSIGN_EVENT_PROFILE", desc="ChatEvent profile reference")
    CHATASSIGN_BOARD_PROFILE = EnvField("CHATASSIGN_BOARD_PROFILE", desc="ChatBoard backend profile reference")
    CHATASSIGN_USER_CHANNEL_PROFILE = EnvField("CHATASSIGN_USER_CHANNEL_PROFILE", desc="User-channel adapter profile reference")
    CHATASSIGN_DEFAULT_POLICY = EnvField("CHATASSIGN_DEFAULT_POLICY", desc="Default assignment policy id")
    CHATASSIGN_DEFAULT_BACKEND = EnvField("CHATASSIGN_DEFAULT_BACKEND", desc="Default backend id")
    CHATASSIGN_CHATBOARD_API_TOKEN = EnvField(
        "CHATASSIGN_CHATBOARD_API_TOKEN",
        desc="ChatBoard API token used by the assignment router",
        is_sensitive=True,
    )
    CHATASSIGN_CHATBOARD_EXECUTOR_TOKEN = EnvField(
        "CHATASSIGN_CHATBOARD_EXECUTOR_TOKEN",
        desc="ChatBoard executor token for real-run handoff",
        is_sensitive=True,
    )
    CHATASSIGN_PUBLIC_LOCAL_ROOT = EnvField("CHATASSIGN_PUBLIC_LOCAL_ROOT", desc="Local root for shareable path resolution")
    CHATASSIGN_PUBLIC_BASE_URL = EnvField("CHATASSIGN_PUBLIC_BASE_URL", desc="Public URL prefix for resolved assignment paths")
    CHATASSIGN_RESOLVER_CONFIG = EnvField("CHATASSIGN_RESOLVER_CONFIG", desc="Optional resolver JSON path")


ChatAssignConfig = ChatassignConfig


__all__ = ["ChatassignConfig", "ChatAssignConfig"]
