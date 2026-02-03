"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class Tf611RepeaterprojectoutputSchemaIn(BaseModel):
    """Input schema for TF611 repeater items."""

    uuid: UUID | None = None
    output: str | int | None = None  # Can be ID or text
    activity: str | int | None = None
    quantity: int | None = None
    unit: str | None = None
    woman_priority: str | int | None = None


class Tf611SchemaIn(BaseModel):
    """Input schema for creating TF611 submissions."""

    # Location fields (from meetinginformation)
    district: str | int | None = None  # Can be ID or text
    administrative_post: str | int | None = None
    suco: str | int | None = None
    aldeia: str | int | None = None

    # Timeframe fields (from projecttimeframe)
    date_start: date | None = None
    date_finish: date | None = None

    # Project details (from projectdetails)
    project_status: str | int | None = None
    project_sector: str | int | None = None
    project_sub_sector: str | int | None = None
    project_name: str | int | None = None
    objective: str | int | None = None
    latitude: Decimal | str | None = None
    longitude: Decimal | str | None = None
    women_priority: str | int | None = None

    # Beneficiaries (from projectbeneficiaries)
    number_of_households: int | None = None
    no_of_women: int | None = None
    no_of_men: int | None = None
    no_of_pwd_male: int | None = None
    no_of_pwd_female: int | None = None

    # Repeater items
    repeaterProjectOutput: List[Tf611RepeaterprojectoutputSchemaIn] | None = Field(
        default=None, alias="repeaterProjectOutput"
    )


Tf611SchemaIn.update_forward_refs()
Tf611RepeaterprojectoutputSchemaIn.update_forward_refs()
