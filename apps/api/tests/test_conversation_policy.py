from app.services.conversation_policy import (
    audit_assistant_reply,
    conversation_policy_prompt,
    is_near_repeat,
)


def test_policy_prompt_contains_center_terminal_rule():
    prompt = conversation_policy_prompt("center")
    assert "договор согласован" in prompt
    assert "продолжить в другом звонке" in prompt


def test_near_repeat_detects_rephrased_duplicate():
    assert is_near_repeat(
        "Пришлите паспорт и документы от приставов.",
        "Пришлите паспорт и документы от приставов.",
    )


def test_audit_flags_long_call_reply_and_repeat():
    result = audit_assistant_reply(
        reply="Первое. Второе. Третье. Четвёрто.",
        previous_assistant_replies=["Первое. Второе. Третье. Четвёрто."],
        mode="call",
    )
    codes = {v.code for v in result.violations}
    assert "too_long" in codes
    assert "near_repeat" in codes


def test_audit_accepts_next_step_chat_reply():
    result = audit_assistant_reply(
        reply="Зафиксировал доход. Дальше уточню, есть ли исполнительные производства.",
        mode="chat",
    )
    assert result.is_ok
