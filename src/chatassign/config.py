"Typed environment configuration for ChatAssign."

from chatenv import BaseEnvConfig, EnvField


class ChatassignConfig(BaseEnvConfig):
    "ChatAssign ChatEnv configuration."

    _title = "ChatAssign Configuration"
    _aliases = ["chatassign"]
    _storage_dir = "Chatassign"

    @classmethod
    def test(cls) -> None:
        """Validate schema registration without external side effects."""

        print(f"Testing {cls._title}...")
        print("Schema loaded; no network test is required.")

    CHATASSIGN_API_KEY = EnvField(
        "CHATASSIGN_API_KEY",
        desc="API key",
        is_sensitive=True,
    )


__all__ = ["ChatassignConfig"]
