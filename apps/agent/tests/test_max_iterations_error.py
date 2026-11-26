from worker.openhands_runner import _is_max_iterations_error


def test_max_iterations_error_detected() -> None:
    exc = RuntimeError(
        "Conversation run failed for id=abc: MaxIterationsReached: "
        "Agent reached maximum iterations limit (80)."
    )
    assert _is_max_iterations_error(exc)


def test_other_errors_are_not_max_iterations() -> None:
    assert not _is_max_iterations_error(RuntimeError("connection reset"))