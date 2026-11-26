from worker.liara_models import liara_user_error_message


def test_liara_500_huge_context_hint() -> None:
    exc = Exception(
        "LLMServiceUnavailableError: litellm.InternalServerError: "
        "Error code: 500 - {'statusCode': 500, 'error': 'Internal Server Error'}"
    )
    msg = liara_user_error_message(exc, liara_model="deepseek/deepseek-v4.1-flash-1017")
    assert "خیلی بزرگ" in msg