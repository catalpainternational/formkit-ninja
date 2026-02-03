"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from ninja import Schema


class Tf611RepeaterprojectoutputSchema(Schema):
    """Output schema for TF611 repeater items."""

    uuid: UUID | None = None
    output: str | None = None
    activity: str | None = None
    quantity: int | None = None
    unit: str | None = None
    woman_priority: str | None = None
    ordinality: int | None = None


class Tf611Schema(Schema):
    """Output schema for TF611 main model."""

    # Location fields (from meetinginformation)
    district: str | None = None
    administrative_post: str | None = None
    suco: str | None = None
    aldeia: str | None = None

    # Timeframe fields (from projecttimeframe)
    date_start: date | None = None
    date_finish: date | None = None

    # Project details (from projectdetails)
    project_status: str | None = None
    project_sector: str | None = None
    project_sub_sector: str | None = None
    project_name: str | None = None
    objective: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    women_priority: str | None = None

    # Beneficiaries (from projectbeneficiaries)
    number_of_households: int | None = None
    no_of_women: int | None = None
    no_of_men: int | None = None
    no_of_pwd_male: int | None = None
    no_of_pwd_female: int | None = None

    # Repeater items
    project_outputs: List[Tf611RepeaterprojectoutputSchema] | None = None


Tf611Schema.update_forward_refs()
Tf611RepeaterprojectoutputSchema.update_forward_refs()
