"""
Notification helpers for optional integrations like Sentry.
"""

from __future__ import annotations

import importlib
from importlib.util import find_spec
from typing import Protocol


class Notifier(Protocol):
    """Protocol for sending notifications."""

    def notify(self, message: str) -> None:
        """Send a message to the notification backend."""


class NullNotifier:
    """No-op notifier for when integrations are unavailable."""

    def notify(self, message: str) -> None:
        return None


class SentryNotifier:
    """Notifier that sends messages to sentry_sdk if available."""

    def __init__(self, sentry_sdk: object) -> None:
        self._sentry_sdk = sentry_sdk

    def notify(self, message: str) -> None:
        if hasattr(self._sentry_sdk, "capture_message"):
            self._sentry_sdk.capture_message(message)


def get_default_notifier() -> Notifier:
    """Return the best available notifier for this runtime."""
    if find_spec("sentry_sdk"):
        sentry_sdk = importlib.import_module("sentry_sdk")
        return SentryNotifier(sentry_sdk)
    return NullNotifier()
