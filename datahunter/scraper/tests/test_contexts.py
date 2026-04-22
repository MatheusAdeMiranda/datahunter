import logging

import pytest

from scraper.app.core.contexts import BrowserContext, Session, managed_session

# ── managed_session ───────────────────────────────────────────────────────────


class TestManagedSession:
    def test_yields_session_object(self) -> None:
        with managed_session("https://example.com") as session:
            assert isinstance(session, Session)

    def test_session_url_matches_argument(self) -> None:
        with managed_session("https://example.com") as session:
            assert session.url == "https://example.com"

    def test_session_is_open_inside_block(self) -> None:
        with managed_session("https://example.com") as session:
            assert session.is_open is True

    def test_session_is_closed_after_block(self) -> None:
        with managed_session("https://example.com") as session:
            pass
        assert session.is_open is False

    def test_default_headers_are_empty(self) -> None:
        with managed_session("https://example.com") as session:
            assert session.headers == {}

    def test_custom_headers_are_forwarded(self) -> None:
        hdrs = {"User-Agent": "datahunter/1.0"}
        with managed_session("https://example.com", headers=hdrs) as session:
            assert session.headers == hdrs

    def test_exception_propagates(self) -> None:
        with pytest.raises(ValueError, match="boom"), managed_session("https://example.com"):
            raise ValueError("boom")

    def test_session_closed_even_after_exception(self) -> None:
        captured: list[Session] = []
        with pytest.raises(ValueError), managed_session("https://example.com") as session:
            captured.append(session)
            raise ValueError("oops")
        assert captured[0].is_open is False

    def test_logs_open_and_close(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.DEBUG, logger="scraper.app.core.contexts"),
            managed_session("https://example.com"),
        ):
            pass
        assert "session opened" in caplog.text
        assert "session closed" in caplog.text

    def test_logs_url(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.DEBUG, logger="scraper.app.core.contexts"),
            managed_session("https://example.com"),
        ):
            pass
        assert "example.com" in caplog.text


# ── BrowserContext ────────────────────────────────────────────────────────────


class TestBrowserContext:
    def test_enter_returns_self(self) -> None:
        ctx = BrowserContext()
        with ctx as browser:
            assert browser is ctx

    def test_is_open_inside_block(self) -> None:
        with BrowserContext() as browser:
            assert browser.is_open is True

    def test_is_closed_after_block(self) -> None:
        with BrowserContext() as browser:
            pass
        assert browser.is_open is False

    def test_exception_propagates_by_default(self) -> None:
        with pytest.raises(RuntimeError, match="crash"), BrowserContext():
            raise RuntimeError("crash")

    def test_is_closed_after_exception(self) -> None:
        ctx = BrowserContext()
        with pytest.raises(RuntimeError), ctx:
            raise RuntimeError("crash")
        assert ctx.is_open is False

    def test_suppress_listed_exception(self) -> None:
        with BrowserContext(suppress=(ValueError,)):
            raise ValueError("suppressed — should not propagate")

    def test_does_not_suppress_unlisted_exception(self) -> None:
        with pytest.raises(TypeError), BrowserContext(suppress=(ValueError,)):
            raise TypeError("not suppressed")

    def test_suppress_subclass_exception(self) -> None:
        class MyError(ValueError):
            pass

        with BrowserContext(suppress=(ValueError,)):
            raise MyError("subclass — also suppressed")

    def test_default_headless_is_true(self) -> None:
        assert BrowserContext().headless is True

    def test_default_timeout(self) -> None:
        assert BrowserContext().timeout == 30.0

    def test_custom_headless(self) -> None:
        assert BrowserContext(headless=False).headless is False

    def test_custom_timeout(self) -> None:
        assert BrowserContext(timeout=60.0).timeout == 60.0

    def test_reusable_across_multiple_withs(self) -> None:
        ctx = BrowserContext()
        with ctx:
            assert ctx.is_open
        assert not ctx.is_open
        with ctx:
            assert ctx.is_open
        assert not ctx.is_open

    def test_logs_open_and_close(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.DEBUG, logger="scraper.app.core.contexts"),
            BrowserContext(),
        ):
            pass
        assert "browser opened" in caplog.text
        assert "browser closed" in caplog.text

    def test_logs_headless_flag(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            caplog.at_level(logging.DEBUG, logger="scraper.app.core.contexts"),
            BrowserContext(headless=False),
        ):
            pass
        assert "headless=False" in caplog.text
