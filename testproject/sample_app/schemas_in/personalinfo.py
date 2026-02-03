"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field, validator


class PersonalInfoSchema(BaseModel):
    full_name: str | None = None
    email_address: str | None = None


PersonalInfoSchema.update_forward_refs()
