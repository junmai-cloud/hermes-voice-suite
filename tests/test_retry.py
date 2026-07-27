from voice_suite.retry import retry_call


def test_retry_call_retries_once_then_returns():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary")
        return "ok"

    assert retry_call(flaky, retries=1, delay_seconds=0) == "ok"
    assert len(calls) == 2


def test_retry_call_does_not_retry_beyond_budget():
    calls = []

    def broken():
        calls.append(1)
        raise RuntimeError("broken")

    try:
        retry_call(broken, retries=1, delay_seconds=0)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected failure")
    assert len(calls) == 2
