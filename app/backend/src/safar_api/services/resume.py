from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import FollowUpResume
from safar_api.services.llm import secondary_llm


def parse_follow_up_resume(questions: list[str], user_message: str) -> dict[str, str]:
    """Map natural-language reply to {question: answer} for LangGraph resume."""
    if not questions:
        return {"response": user_message}

    llm = secondary_llm().with_structured_output(FollowUpResume)
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    result = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Extract answers to the numbered follow-up questions from the user's message. "
                    "Use the exact question text as keys in the answers object. "
                    "If the user answered in one sentence covering multiple items, split appropriately."
                )
            ),
            HumanMessage(
                content=f"Questions:\n{numbered}\n\nUser reply:\n{user_message}"
            ),
        ]
    )
    if result.answers:
        return result.answers
    return {questions[0]: user_message}
