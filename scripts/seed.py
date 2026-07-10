#!/usr/bin/env python3
"""Seed the pipeline with Faker-generated clinical notes for demo runs."""

import os
import random
import sys

import httpx
from faker import Faker

fake = Faker()

_TEMPLATES = [
    (
        "Patient {name}, DOB {dob}, SSN {ssn}, presented on {date} with chief complaint "
        "of chest pain radiating to the left arm. MRN {mrn}. Residential address: {address}. "
        "Contact: {phone}. Attending: Dr. {doctor}. Assessment: rule out ACS."
    ),
    (
        "Discharge summary for {name} (DOB {dob}). Admission date: {date}. "
        "MRN {mrn}. SSN {ssn}. Address: {address}. Emergency contact: {phone}. "
        "Primary care physician: Dr. {doctor}. Diagnosis: type 2 diabetes mellitus."
    ),
    (
        "Lab order for patient {name}, MRN {mrn}. Date of birth: {dob}. "
        "Collection date: {date}. Ordering physician: Dr. {doctor}. "
        "Patient SSN: {ssn}. Callback number: {phone}. "
        "Tests ordered: CBC, CMP, HbA1c."
    ),
    (
        "Referral to cardiology for {name} (SSN {ssn}). DOB: {dob}. "
        "Appointment requested: {date}. MRN: {mrn}. "
        "Home address: {address}. Phone: {phone}. "
        "Referring provider: Dr. {doctor}."
    ),
    (
        "Prescription: Patient {name}, DOB {dob}, MRN {mrn}. "
        "Prescribed on {date} by Dr. {doctor}. "
        "Address: {address}. Phone: {phone}. "
        "Medication: Metformin 500 mg twice daily with meals."
    ),
]


def _make_record() -> dict:
    template = random.choice(_TEMPLATES)
    text = template.format(
        name=fake.name(),
        dob=fake.date_of_birth(minimum_age=18, maximum_age=90).strftime("%m/%d/%Y"),
        ssn=fake.ssn(),
        date=fake.date_this_year().strftime("%m/%d/%Y"),
        mrn=f"MRN {fake.numerify('########')}",
        address=fake.address().replace("\n", ", "),
        phone=fake.phone_number(),
        doctor=fake.last_name(),
    )
    return {"id": f"seed-{fake.uuid4()}", "text": text}


def main() -> None:
    api_url = os.getenv("API_URL", "http://localhost:8000")
    count = int(os.getenv("SEED_COUNT", "20"))

    records = [_make_record() for _ in range(count)]

    print(f"Seeding {count} synthetic PHI records to {api_url}/ingest ...")
    try:
        resp = httpx.post(f"{api_url}/ingest", json={"records": records}, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    print(f"Job ID     : {data['job_id']}")
    print(f"Records    : {data['record_count']}")
    print(f"Poll status: GET {api_url}/records/{data['job_id']}")


if __name__ == "__main__":
    main()
