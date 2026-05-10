"""Voice pipeline errors (no secrets in messages)."""


class VoiceConfigurationError(Exception):
    """Runtime voice config from settings is missing or incomplete."""

    def __init__(self, message: str, *, code: str = "voice_config") -> None:
        super().__init__(message)
        self.code = code
