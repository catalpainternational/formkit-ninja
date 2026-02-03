"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from ninja import Router

from .. import models
from .. import schemas as schema_out
from .. import schemas_in as schema_in
from formkit_ninja.form_submission.models import Submission, SeparatedSubmission

router = Router(tags=["tf611"])


@router.get("tf611", response=list[schema_out.Tf611Schema], exclude_none=True)
def list_tf611(request):
    """
    List all TF611 submissions.

    Returns all TF611 records with their project outputs included.
    """
    queryset = models.Tf611.objects.all()
    queryset = queryset.prefetch_related("project_outputs")
    return queryset


@router.get("tf611/{submission_id}", response=schema_out.Tf611Schema, exclude_none=True)
def get_tf611(request, submission_id: str):
    """
    Get a single TF611 submission by ID.
    """
    instance = models.Tf611.objects.prefetch_related("project_outputs").get(
        submission_id=submission_id
    )
    return instance


@router.post("tf611", response=schema_out.Tf611Schema)
def create_tf611(request, payload: schema_in.Tf611SchemaIn):
    """
    Create a new TF611 submission.

    Accepts the form data as JSON and creates:
    1. A Submission record
    2. SeparatedSubmission records (main + repeaters)
    3. Django model instances via signal handlers

    Returns the created TF611 record.
    """
    data = payload.dict(exclude_unset=True, by_alias=True)

    # Create a Submission entry
    submission = Submission.objects.create(
        fields=data,
        form_type="Tf611",
    )

    # The signal handlers should have run synchronously.
    # We need to find the specific model instance that was created.
    try:
        # For the root object, repeater_parent is None and form_type matches
        sep_sub = SeparatedSubmission.objects.get(
            submission=submission, form_type="Tf611", repeater_parent__isnull=True
        )

        # Get the model instance linked to it
        instance = models.Tf611.objects.prefetch_related("project_outputs").get(
            submission=sep_sub
        )
        return instance

    except (SeparatedSubmission.DoesNotExist, models.Tf611.DoesNotExist):
        # Fallback or error handling
        raise Exception("Submission processing failed or model not created.")
