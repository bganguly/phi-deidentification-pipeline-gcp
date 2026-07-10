from __future__ import annotations

import json
import logging

import anthropic

from app.core.config import settings
from app.phi.detector import DetectedEntity

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a PHI detection expert for clinical records. "
    "Identify all Protected Health Information (PHI) in the provided text. "
    "Return ONLY a valid JSON array. Each element must have: "
    "text (string), label (one of: PERSON/DATE/SSN/PHONE/MRN/EMAIL/GPE/LOC/ORG), "
    "start (int character offset), end (int character offset), confidence (float 0-1). "
    "Return [] if no PHI is found. No explanation, no markdown — raw JSON only."
)


def detect_phi_claude(text: str) -> list[DetectedEntity]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Clinical text:\n\n{text}"}],
    )

    raw = message.content[0].text.strip()
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("claude returned non-JSON: %.200s", raw)
        return []

    results: list[DetectedEntity] = []
    for item in items:
        try:
            results.append(DetectedEntity(
                text=item["text"],
                label=item["label"],
                start=int(item["start"]),
                end=int(item["end"]),
                confidence=float(item.get("confidence", 0.88)),
                source="claude",
            ))
        except (KeyError, TypeError, ValueError):
            logger.warning("skipping malformed entity from claude: %s", item)

    return results
