"""Present model reasoning and attach trusted citation numbers; no policy templates."""

from app.models import PolicyResponse


def render_answer(response: PolicyResponse) -> str:
    numbers = {sid: i + 1 for i, sid in enumerate(response.section_ids)}
    paragraphs = [
        point.text + " " + " ".join(f"[{numbers[sid]}]" for sid in point.section_ids)
        for point in response.points
    ]
    prefix = {"yes": "Yes. ", "no": "No. ", "conditional": "It depends. "}.get(response.verdict, "")
    return prefix + "\n\n".join(paragraphs)
