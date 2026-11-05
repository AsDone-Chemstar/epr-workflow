"""Qt-free status event model and message resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from spectralab.app.gui.i18n import Translator

STATUS_LEVELS = ("success", "info", "warning", "error")


class StatusError(ValueError):
    """An invalid status event was supplied."""


@dataclass(frozen=True)
class StatusEvent:
    level: str
    key: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    text: str | None = None

    def __post_init__(self) -> None:
        if self.level not in STATUS_LEVELS:
            raise StatusError(f"Unsupported status level: {self.level!r}")
        if self.key is not None and (not isinstance(self.key, str) or not self.key):
            raise StatusError("Status key must be non-empty text or None.")
        if self.text is not None and not isinstance(self.text, str):
            raise StatusError("Status text must be text or None.")
        if self.key is None and self.text is None:
            raise StatusError("Status event needs a key or text.")

    def message(self, translator: Translator) -> str:
        if self.text is not None:
            return self.text
        return translator.tr(str(self.key), **dict(self.params))


def status_from_payload(payload: Any) -> StatusEvent:
    """Convert a panel-emitted dict or StatusEvent into a StatusEvent."""
    if isinstance(payload, StatusEvent):
        return payload
    if not isinstance(payload, Mapping):
        raise StatusError("Panel status payload must be a status event or mapping.")
    level = payload.get("level", "info")
    if not isinstance(level, str):
        raise StatusError("Status level must be text.")
    key = payload.get("key")
    text = payload.get("text")
    params = payload.get("params", {})
    if not isinstance(params, Mapping):
        raise StatusError("Status params must be a mapping.")
    return StatusEvent(
        level=level,
        key=key,
        params=dict(params),
        text=text,
    )


__all__ = [
    "STATUS_LEVELS",
    "StatusError",
    "StatusEvent",
    "status_from_payload",
]
