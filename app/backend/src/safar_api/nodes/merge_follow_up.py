import json

from langchain_core.messages import HumanMessage, SystemMessage

from safar_api.models.schemas import StructuredTravelExtract
from safar_api.models.state import TravelState
from safar_api.nodes.follow_up_fields import apply_follow_up_to_structured, with_planning_defaults
from safar_api.services.llm import secondary_llm

_merge_llm = secondary_llm().with_structured_output(
    StructuredTravelExtract,
    method="function_calling",
)


def merge_follow_up_structured(state: TravelState) -> dict:
    structured = dict(state.structured or {})
    answers = dict(state.follow_up_answers or {})
    if not answers:
        merged = with_planning_defaults(structured)
        return {"structured": merged, "follow_up_index": 0}

    qa_block = "\n".join(
        f"{field}: {text}" for field, text in answers.items()
    )
    prompt = """
        Merge the follow-up answers into a complete structured travel profile.
        Fill only fields that are still null or empty. Use enum values for budget, travel_style,
        and mode_of_transport. Use ISO dates for date_range when possible.
        Do not invent values the user did not provide.
        """

    result = _merge_llm.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(
                content=(
                    f"Partial structured data:\n{json.dumps(structured, default=str)}\n\n"
                    f"Follow-up answers by field:\n{qa_block}"
                )
            ),
        ]
    )

    merged = {**structured, **result.model_dump(exclude_none=True)}
    merged = apply_follow_up_to_structured(merged)
    merged = with_planning_defaults(merged)
    merged["follow_up_answers"] = answers

    return {
        "structured": merged,
        "follow_up_answers": answers,
        "follow_up_index": 0,
    }
