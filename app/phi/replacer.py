from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from faker import Faker

_fake = Faker()


def synthetic_replacement(original: str, entity_type: str) -> str:
    match entity_type:
        case "PERSON":
            return _fake.name()
        case "DATE":
            return _shifted_date(original)
        case "SSN":
            return _fake.ssn()
        case "MRN":
            return f"MRN-{_fake.numerify('########')}"
        case "PHONE":
            return _fake.phone_number()
        case "EMAIL":
            return _fake.email()
        case "GPE" | "LOC" | "ADDRESS":
            return _fake.city()
        case "ORG":
            return _fake.company()
        case _:
            return f"[{entity_type}]"


def hash_phi(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _shifted_date(original: str) -> str:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(original.strip(), fmt)
            shifted = dt + timedelta(days=random.randint(-30, 30))
            return shifted.strftime(fmt)
        except ValueError:
            continue
    return _fake.date()
