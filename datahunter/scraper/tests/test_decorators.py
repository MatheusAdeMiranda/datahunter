import logging
from unittest.mock import call, patch

import pytest

from scraper.app.core.decorators import log_execution, rate_limit, retry
from scraper.app.core.exceptions import NetworkError

# ── retry ─────────────────────────────────────────────────────────────────────


class TestRetry:
    def test_returns_on_first_success(self) -> None:
        @retry(times=3, exceptions=(ValueError,))
        def fn() -> int:
            return 42

        assert fn() == 42

    def test_retries_on_matching_exception(self) -> None:
        calls = 0

        @retry(times=3, exceptions=(ValueError,))
        def fn() -> None:
            nonlocal calls
            calls += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            fn()
        assert calls == 3

    def test_raises_after_exhausting_retries(self) -> None:
        @retry(times=2, exceptions=(ValueError,))
        def fn() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fn()

    def test_eventual_success_returns_value(self) -> None:
        calls = 0

        @retry(times=3, exceptions=(ValueError,))
        def fn() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("not yet")
            return "ok"

        assert fn() == "ok"
        assert calls == 3

    def test_does_not_catch_unspecified_exception(self) -> None:
        calls = 0

        @retry(times=3, exceptions=(ValueError,))
        def fn() -> None:
            nonlocal calls
            calls += 1
            raise TypeError("different error")

        with pytest.raises(TypeError):
            fn()
        assert calls == 1

    def test_preserves_function_metadata(self) -> None:
        @retry(times=2, exceptions=(ValueError,))
        def my_function() -> None:
            """Docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Docstring."

    def test_no_sleep_when_backoff_base_is_zero(self) -> None:
        @retry(times=3, exceptions=(ValueError,), backoff_base=0.0)
        def fn() -> None:
            raise ValueError

        with patch("scraper.app.core.decorators.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                fn()
        mock_sleep.assert_not_called()

    def test_exponential_backoff_delays(self) -> None:
        @retry(times=4, exceptions=(ValueError,), backoff_base=1.0)
        def fn() -> None:
            raise ValueError

        with patch("scraper.app.core.decorators.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                fn()
        # 3 sleeps for attempts 1, 2, 3 (not after last attempt)
        assert mock_sleep.call_args_list == [call(1.0), call(2.0), call(4.0)]

    def test_backoff_not_called_after_last_attempt(self) -> None:
        @retry(times=2, exceptions=(ValueError,), backoff_base=1.0)
        def fn() -> None:
            raise ValueError

        with patch("scraper.app.core.decorators.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                fn()
        # only 1 sleep (after attempt 1, not after attempt 2 which is the last)
        mock_sleep.assert_called_once_with(1.0)

    def test_backoff_not_called_on_success(self) -> None:
        calls = 0

        @retry(times=3, exceptions=(ValueError,), backoff_base=1.0)
        def fn() -> str:
            nonlocal calls
            calls += 1
            if calls < 2:
                raise ValueError
            return "ok"

        with patch("scraper.app.core.decorators.time.sleep") as mock_sleep:
            result = fn()
        assert result == "ok"
        mock_sleep.assert_called_once_with(1.0)

    def test_works_with_domain_exception(self) -> None:
        calls = 0

        @retry(times=3, exceptions=(NetworkError,))
        def fetch() -> str:
            nonlocal calls
            calls += 1
            if calls < 2:
                raise NetworkError("timeout")
            return "data"

        assert fetch() == "data"
        assert calls == 2


# ── rate_limit ────────────────────────────────────────────────────────────────


class TestRateLimit:
    def test_allows_calls_within_limit(self) -> None:
        @rate_limit(calls=3, period=1.0)
        def fn() -> None:
            pass

        with (
            patch("scraper.app.core.decorators.time.sleep") as mock_sleep,
            patch("scraper.app.core.decorators.time.monotonic", return_value=0.0),
        ):
            fn()
            fn()
            fn()
        mock_sleep.assert_not_called()

    def test_sleeps_when_limit_exceeded(self) -> None:
        @rate_limit(calls=1, period=1.0)
        def fn() -> None:
            pass

        with (
            patch("scraper.app.core.decorators.time.sleep") as mock_sleep,
            patch("scraper.app.core.decorators.time.monotonic", return_value=0.0),
        ):
            fn()
            fn()
        mock_sleep.assert_called_once_with(1.0)

    def test_old_timestamps_are_purged(self) -> None:
        @rate_limit(calls=1, period=1.0)
        def fn() -> None:
            pass

        t = 0.0

        def advance() -> float:
            return t

        with patch("scraper.app.core.decorators.time.sleep"):
            with patch("scraper.app.core.decorators.time.monotonic", side_effect=advance):
                fn()  # t=0.0 → timestamps=[0.0]

            t = 2.0  # jump past the period

            with (
                patch("scraper.app.core.decorators.time.monotonic", return_value=2.0),
                patch("scraper.app.core.decorators.time.sleep") as mock_sleep_2,
            ):
                fn()  # t=2.0, 0.0 <= 2.0-1.0=1.0 → purge → no sleep
        mock_sleep_2.assert_not_called()

    def test_purges_timestamps_after_sleeping(self) -> None:
        @rate_limit(calls=1, period=1.0)
        def fn() -> None:
            pass

        # first call at t=0.5; second call also at t=0.5 → sleep
        # after sleep, monotonic returns 2.0 → 0.5 <= 2.0-1.0=1.0 → purge
        monotonic_values = iter([0.5, 0.5, 0.5, 2.0, 2.0])
        with (
            patch("scraper.app.core.decorators.time.sleep") as mock_sleep,
            patch("scraper.app.core.decorators.time.monotonic", side_effect=monotonic_values),
        ):
            fn()
            fn()
        mock_sleep.assert_called_once_with(1.0)

    def test_preserves_function_metadata(self) -> None:
        @rate_limit(calls=1, period=1.0)
        def my_function() -> None:
            """Docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Docstring."


# ── log_execution ─────────────────────────────────────────────────────────────


class TestLogExecution:
    def test_returns_function_result(self) -> None:
        @log_execution
        def fn() -> int:
            return 99

        assert fn() == 99

    def test_reraises_exception(self) -> None:
        @log_execution
        def fn() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fn()

    def test_logs_on_success(self, caplog: pytest.LogCaptureFixture) -> None:
        @log_execution
        def fn() -> None:
            pass

        with caplog.at_level(logging.DEBUG, logger="scraper.app.core.decorators"):
            fn()

        assert "calling fn" in caplog.text
        assert "fn finished" in caplog.text

    def test_logs_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        @log_execution
        def fn() -> None:
            raise ValueError

        with (
            caplog.at_level(logging.DEBUG, logger="scraper.app.core.decorators"),
            pytest.raises(ValueError),
        ):
            fn()

        assert "fn raised" in caplog.text

    def test_preserves_function_metadata(self) -> None:
        @log_execution
        def my_function() -> None:
            """Docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Docstring."


# ── stacking ──────────────────────────────────────────────────────────────────


class TestStacking:
    def test_retry_logs_each_attempt(self, caplog: pytest.LogCaptureFixture) -> None:
        calls = 0

        @retry(times=3, exceptions=(ValueError,))
        @log_execution
        def fn() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("not yet")
            return "done"

        with caplog.at_level(logging.DEBUG, logger="scraper.app.core.decorators"):
            result = fn()

        assert result == "done"
        assert calls == 3
        assert caplog.text.count("calling fn") == 3

    def test_metadata_survives_stacking(self) -> None:
        @retry(times=2, exceptions=(ValueError,))
        @log_execution
        def my_function() -> None:
            """Docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Docstring."
