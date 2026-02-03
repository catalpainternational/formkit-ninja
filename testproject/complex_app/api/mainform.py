"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from ninja import Router

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission

from .. import models
from .. import schemas as schema_out
from .. import schemas_in as schema_in

router = Router(tags=["forms"])


@router.get("mainform", response=list[schema_out.MainFormSchema], exclude_none=True)
def mainform(request):
    # Schema includes fields: title description
    queryset = models.MainForm.objects.all()
    queryset = queryset.prefetch_related(
        "line_items",
    )
    return queryset


@router.post("mainform", response=schema_out.MainFormSchema)
def create_mainform(request, payload: schema_in.MainFormSchema):
    data = payload.dict(exclude_unset=True)

    # Create a Submission entry
    submission = Submission.objects.create(
        fields=data,
        form_type="MainForm",
    )

    # The signal handlers should have run synchronously.
    # We need to find the specific model instance that was created.
    # 1. Find the parent SeparatedSubmission
    try:
        # For the root object, repeater_parent is None and form_type matches
        sep_sub = SeparatedSubmission.objects.get(
            submission=submission, form_type="MainForm", repeater_parent__isnull=True
        )

        # 2. Get the model instance linked to it
        instance = models.MainForm.objects.get(submission=sep_sub)
        return instance

    except (SeparatedSubmission.DoesNotExist, models.MainForm.DoesNotExist):
        # Fallback or error handling
        # If signal failed or async, we might return something else or 202 Accepted
        # But here we expect synchronous success
        raise Exception("Submission processing failed or model not created.")


@router.get("mainformlineitems", response=list[schema_out.MainFormLineItemsSchema], exclude_none=True)
def mainformlineitems(request):
    # Schema includes fields: item_name quantity price
    queryset = models.MainFormLineItems.objects.all()
    return queryset


@router.post("mainformlineitems", response=schema_out.MainFormLineItemsSchema)
def create_mainformlineitems(request, payload: schema_in.MainFormLineItemsSchema):
    data = payload.dict(exclude_unset=True)

    # Create a Submission entry
    submission = Submission.objects.create(
        fields=data,
        form_type="MainFormLineItems",
    )

    # The signal handlers should have run synchronously.
    # We need to find the specific model instance that was created.
    # 1. Find the parent SeparatedSubmission
    try:
        # For the root object, repeater_parent is None and form_type matches
        sep_sub = SeparatedSubmission.objects.get(
            submission=submission, form_type="MainFormLineItems", repeater_parent__isnull=True
        )

        # 2. Get the model instance linked to it
        instance = models.MainFormLineItems.objects.get(submission=sep_sub)
        return instance

    except (SeparatedSubmission.DoesNotExist, models.MainFormLineItems.DoesNotExist):
        # Fallback or error handling
        # If signal failed or async, we might return something else or 202 Accepted
        # But here we expect synchronous success
        raise Exception("Submission processing failed or model not created.")
