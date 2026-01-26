"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema


class Tf_6_1_1MeetinginformationSchema(Schema):
    district: str | None = None
    administrative_post: str | None = None
    suco: str | None = None
    aldeia: str | None = None


class Tf_6_1_1ProjecttimeframeSchema(Schema):
    date_start_estimated: datetime | None = None
    date_finish_estimated: datetime | None = None


class Tf_6_1_1ProjectdetailsSchema(Schema):
    project_status: str | None = None
    project_sector: str | None = None
    project_subsector: str | None = None
    project_name: str | None = None
    objective: str | None = None
    gps_latitude: int | None = None
    gps_longitude: int | None = None
    is_women_priority: str | None = None


class Tf_6_1_1ProjectbeneficiariesSchema(Schema):
    number_of_households: int | None = None
    no_of_women: int | None = None
    no_of_men: int | None = None
    disability_male: int | None = None
    disability_female: int | None = None


class Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema(Schema):
    uuid: UUID | None = None
    ordinality: int


class Tf_6_1_1ProjectoutputSchema(Schema):
    repeaterProjectOutput: list[Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema] | None = None


class Tf_6_1_1Schema(Schema):
    meetinginformation: Tf_6_1_1Meetinginformation | None = None
    projecttimeframe: Tf_6_1_1Projecttimeframe | None = None
    projectdetails: Tf_6_1_1Projectdetails | None = None
    projectbeneficiaries: Tf_6_1_1Projectbeneficiaries | None = None
    projectoutput: Tf_6_1_1Projectoutput | None = None


class Tf_6_1_1MeetinginformationSchema(Schema):
    district: str | None = None
    administrative_post: str | None = None
    suco: str | None = None
    aldeia: str | None = None


class Tf_6_1_1ProjecttimeframeSchema(Schema):
    date_start_estimated: datetime | None = None
    date_finish_estimated: datetime | None = None


class Tf_6_1_1ProjectdetailsSchema(Schema):
    project_status: str | None = None
    project_sector: str | None = None
    project_subsector: str | None = None
    project_name: str | None = None
    objective: str | None = None
    gps_latitude: int | None = None
    gps_longitude: int | None = None
    is_women_priority: str | None = None


class Tf_6_1_1ProjectbeneficiariesSchema(Schema):
    number_of_households: int | None = None
    no_of_women: int | None = None
    no_of_men: int | None = None
    disability_male: int | None = None
    disability_female: int | None = None


class Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema(Schema):
    uuid: UUID | None = None
    ordinality: int


class Tf_6_1_1ProjectoutputSchema(Schema):
    repeaterProjectOutput: list[Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema] | None = None


class Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema(Schema):
    uuid: UUID | None = None
    ordinality: int
