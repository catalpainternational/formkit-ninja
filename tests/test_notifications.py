from types import SimpleNamespace

import pytest

from formkit_ninja.notifications import NullNotifier, SentryNotifier, get_default_notifier


def test_null_notifier_noop() -> None:
    notifier = NullNotifier()

    notifier.notify("ignored")


def test_sentry_notifier_calls_capture_message() -> None:
    calls: list[str] = []

    def capture_message(message: str) -> None:
        calls.append(message)

    sentry_sdk = SimpleNamespace(capture_message=capture_message)
    notifier = SentryNotifier(sentry_sdk)

    notifier.notify("hello")

    assert calls == ["hello"]


def test_get_default_notifier_returns_null_when_missing_sentry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("formkit_ninja.notifications.find_spec", lambda _: None)

    notifier = get_default_notifier()

    assert isinstance(notifier, NullNotifier)
