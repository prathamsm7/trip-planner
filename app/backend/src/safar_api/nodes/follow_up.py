from langgraph.types import interrupt

from safar_api.models.state import TravelState
from safar_api.nodes.follow_up_fields import (
    FIELD_QUESTIONS,
    apply_field_answer,
    apply_follow_up_to_structured,
    pending_fields,
)


def conversational_follow_up_message(question: str, index: int, total: int) -> str:
    if index == 0:
        prefix = "I'd love to help plan your trip. "
    elif index == total - 1:
        prefix = "Almost there — "
    else:
        prefix = ""
    return f"{prefix}{question}"


def _normalize_answer(answer, field_key: str) -> str:
    if isinstance(answer, str):
        return answer.strip()
    if isinstance(answer, dict):
        if field_key in answer:
            return str(answer[field_key]).strip()
        if answer:
            return str(next(iter(answer.values()))).strip()
    return str(answer).strip()


def follow_up_questions(state: TravelState) -> dict:
    structured = dict(state.structured or {})
    pending = pending_fields(structured)
    if not pending:
        return {}

    field_key = pending[0]
    question = FIELD_QUESTIONS[field_key]
    answers = dict(state.follow_up_answers or {})
    index = len(answers)
    total = index + len(pending)

    answer = interrupt(
        {
            "type": "follow_up",
            "field": field_key,
            "question": question,
            "index": index,
            "total": total,
            "message": conversational_follow_up_message(question, index, total),
        }
    )

    answers[field_key] = _normalize_answer(answer, field_key)
    structured = apply_field_answer(structured, field_key, answers[field_key])
    structured = apply_follow_up_to_structured(structured)

    return {
        "structured": structured,
        "follow_up_answers": answers,
        "follow_up_index": index + 1,
    }


def follow_up_router(state: TravelState) -> str:
    if pending_fields(state.structured or {}):
        return "follow_up_questions"
    return "merge_follow_up_structured"
