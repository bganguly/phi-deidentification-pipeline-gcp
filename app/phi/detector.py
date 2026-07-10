from __future__ import annotations

import re
from dataclasses import dataclass

import spacy

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(
    r"\b(?:\+1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b"
)
_MRN_RE = re.compile(r"\bMRN[:\s#-]*\d{6,10}\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_PHI_LABELS = {"PERSON", "DATE", "GPE", "LOC", "ORG"}

_nlp: spacy.language.Language | None = None


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_sci_md")
    return _nlp


@dataclass
class DetectedEntity:
    text: str
    label: str
    start: int
    end: int
    confidence: float
    source: str


def detect_phi(text: str) -> tuple[list[DetectedEntity], float]:
    nlp = _get_nlp()
    doc = nlp(text)
    entities: list[DetectedEntity] = []

    for ent in doc.ents:
        if ent.label_ in _PHI_LABELS:
            entities.append(DetectedEntity(
                text=ent.text,
                label=ent.label_,
                start=ent.start_char,
                end=ent.end_char,
                confidence=0.90,
                source="spacy",
            ))

    for pattern, label in (
        (_SSN_RE, "SSN"),
        (_PHONE_RE, "PHONE"),
        (_MRN_RE, "MRN"),
        (_EMAIL_RE, "EMAIL"),
    ):
        for m in pattern.finditer(text):
            entities.append(DetectedEntity(
                text=m.group(),
                label=label,
                start=m.start(),
                end=m.end(),
                confidence=0.97,
                source="regex",
            ))

    if not entities:
        # Low confidence triggers Claude fallback for texts with PHI-related keywords
        if re.search(r"\b(?:patient|name|dob|ssn|mrn|address|phone)\b", text, re.IGNORECASE):
            return entities, 0.40
        return entities, 1.0

    return entities, sum(e.confidence for e in entities) / len(entities)
