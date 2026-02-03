"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from ninja import Router

from .. import models
from .. import schemas as schema_out
from .. import schemas_in as schema_in
from formkit_ninja.form_submission.models import Submission, SeparatedSubmission

router = Router(tags=["forms"])


@router.get("personalinfo", response=list[schema_out.PersonalInfoSchema], exclude_none=True)
def personalinfo(request):
    # Schema includes fields: full_name email_address
    queryset = models.PersonalInfo.objects.all()
    return queryset


@router.post("personalinfo", response=schema_out.PersonalInfoSchema)
def create_personalinfo(request, payload: schema_in.PersonalInfoSchema):
    data = payload.dict(exclude_unset=True)

    # Create a Submission entry
    submission = Submission.objects.create(
        fields=data,
        form_type="PersonalInfo",
    )

    # The signal handlers should have run synchronously.
    # We need to find the specific model instance that was created.
    # 1. Find the parent SeparatedSubmission
    try:
        # For the root object, repeater_parent is None and form_type matches
        sep_sub = SeparatedSubmission.objects.get(
            submission=submission, form_type="PersonalInfo", repeater_parent__isnull=True
        )

        # 2. Get the model instance linked to it
        instance = models.PersonalInfo.objects.get(submission=sep_sub)
        return instance

    except (SeparatedSubmission.DoesNotExist, models.PersonalInfo.DoesNotExist):
        # Fallback or error handling
        # If signal failed or async, we might return something else or 202 Accepted
        # But here we expect synchronous success
        raise Exception("Submission processing failed or model not created.")
