from app.llm.openai_params import completion_token_param


def test_gpt5_models_use_max_completion_tokens():
    assert completion_token_param("gpt-5.4-nano", 500) == {"max_completion_tokens": 500}
    assert completion_token_param("gpt-5.5", 3000) == {"max_completion_tokens": 3000}


def test_legacy_chat_models_keep_max_tokens():
    assert completion_token_param("gpt-4o-mini", 500) == {"max_tokens": 500}

