"""Small JSON-backed GUI settings service with safe defaults."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from spectralab.app.gui.i18n import DEFAULT_LANGUAGE, LANGUAGES, normalize_language

DEFAULT_WINDOW_WIDTH = 1100
DEFAULT_WINDOW_HEIGHT = 760
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 480
MAX_WINDOW_SIZE = 10000


class SettingsError(ValueError):
    """A settings file could not be written."""


@dataclass(frozen=True)
class GuiSettings:
    language: str = DEFAULT_LANGUAGE
    active_technique: str | None = None
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT

    def with_language(self, language: str) -> "GuiSettings":
        return replace(self, language=normalize_language(language))

    def with_technique(self, technique_id: str | None) -> "GuiSettings":
        return replace(self, active_technique=technique_id)

    def with_size(self, width: int, height: int) -> "GuiSettings":
        return replace(self, window_width=width, window_height=height)


def _valid_size(value: Any, *, default: int, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    if value < minimum or value > MAX_WINDOW_SIZE:
        return default
    return value


class SettingsService:
    """Read/write GUI preferences without letting malformed JSON crash startup.

    ``load()`` always returns a valid ``GuiSettings`` snapshot. Write failures
    are explicit through :class:`SettingsError`. A ``None`` path means the
    service is memory-only and ``save()`` is a no-op.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self.last_warning: str | None = None

    @property
    def path(self) -> Path | None:
        return self._path

    def load(self) -> GuiSettings:
        self.last_warning = None
        if self._path is None or not self._path.is_file():
            return GuiSettings()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.last_warning = f"Could not read GUI settings: {exc}"
            return GuiSettings()
        if not isinstance(payload, dict):
            self.last_warning = "GUI settings root is not an object."
            return GuiSettings()

        language = payload.get("language", DEFAULT_LANGUAGE)
        if not isinstance(language, str) or language not in LANGUAGES:
            self.last_warning = f"Unsupported saved language: {language!r}"
            language = DEFAULT_LANGUAGE
        else:
            language = normalize_language(language)

        active = payload.get("active_technique")
        if active is not None and (not isinstance(active, str) or not active):
            self.last_warning = "Invalid saved active technique."
            active = None

        return GuiSettings(
            language=language,
            active_technique=active,
            window_width=_valid_size(
                payload.get("window_width"),
                default=DEFAULT_WINDOW_WIDTH,
                minimum=MIN_WINDOW_WIDTH,
            ),
            window_height=_valid_size(
                payload.get("window_height"),
                default=DEFAULT_WINDOW_HEIGHT,
                minimum=MIN_WINDOW_HEIGHT,
            ),
        )

    def save(self, settings: GuiSettings) -> None:
        if not isinstance(settings, GuiSettings):
            raise SettingsError("save() requires GuiSettings.")
        if self._path is None:
            return
        payload = {
            "language": normalize_language(settings.language),
            "active_technique": settings.active_technique,
            "window_width": int(settings.window_width),
            "window_height": int(settings.window_height),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                dir=str(self._path.parent),
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                    json.dump(
                        payload,
                        handle,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self._path)
            finally:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
        except OSError as exc:
            raise SettingsError(f"Could not save GUI settings: {exc}") from exc


__all__ = [
    "DEFAULT_WINDOW_HEIGHT",
    "DEFAULT_WINDOW_WIDTH",
    "GuiSettings",
    "SettingsError",
    "SettingsService",
]
