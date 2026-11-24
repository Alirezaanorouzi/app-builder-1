from worker.liara_models import liara_user_error_message


def test_balance_error_is_liara_not_openai_cloud() -> None:
    exc = Exception(
        "APIError: OpenAIException - Your balance must be higher than 393884 tomans"
    )
    msg = liara_user_error_message(exc, liara_model="deepseek/deepseek-v4.1-flash")
    assert "لیارا" in msg
    assert "OpenAIException" in msg
    assert "api.openai.com وصل نشده" in msg