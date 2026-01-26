"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from ninja import Router

from . import models, schema_out

router = Router(tags=["forms"])


@router.get(
    "tf_6_1_1meetinginformation", response=list[schema_out.Tf_6_1_1MeetinginformationSchema], exclude_none=True
)
def tf_6_1_1meetinginformation(request):
    queryset = models.Tf_6_1_1Meetinginformation.objects.all()
    return queryset


@router.get("tf_6_1_1projecttimeframe", response=list[schema_out.Tf_6_1_1ProjecttimeframeSchema], exclude_none=True)
def tf_6_1_1projecttimeframe(request):
    queryset = models.Tf_6_1_1Projecttimeframe.objects.all()
    return queryset


@router.get("tf_6_1_1projectdetails", response=list[schema_out.Tf_6_1_1ProjectdetailsSchema], exclude_none=True)
def tf_6_1_1projectdetails(request):
    queryset = models.Tf_6_1_1Projectdetails.objects.all()
    return queryset


@router.get(
    "tf_6_1_1projectbeneficiaries", response=list[schema_out.Tf_6_1_1ProjectbeneficiariesSchema], exclude_none=True
)
def tf_6_1_1projectbeneficiaries(request):
    queryset = models.Tf_6_1_1Projectbeneficiaries.objects.all()
    return queryset


@router.get(
    "tf_6_1_1projectoutputrepeaterprojectoutput",
    response=list[schema_out.Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema],
    exclude_none=True,
)
def tf_6_1_1projectoutputrepeaterprojectoutput(request):
    queryset = models.Tf_6_1_1ProjectoutputRepeaterprojectoutput.objects.all()
    return queryset


@router.get("tf_6_1_1projectoutput", response=list[schema_out.Tf_6_1_1ProjectoutputSchema], exclude_none=True)
def tf_6_1_1projectoutput(request):
    queryset = models.Tf_6_1_1Projectoutput.objects.all()
    queryset = queryset.prefetch_related(
        "repeaterProjectOutput",
    )
    return queryset


@router.get("tf_6_1_1", response=list[schema_out.Tf_6_1_1Schema], exclude_none=True)
def tf_6_1_1(request):
    queryset = models.Tf_6_1_1.objects.all()
    queryset = queryset.select_related(
        "meetinginformation",
        "projecttimeframe",
        "projectdetails",
        "projectbeneficiaries",
        "projectoutput",
    )
    return queryset


@router.get(
    "tf_6_1_1meetinginformation", response=list[schema_out.Tf_6_1_1MeetinginformationSchema], exclude_none=True
)
def tf_6_1_1meetinginformation(request):
    queryset = models.Tf_6_1_1Meetinginformation.objects.all()
    return queryset


@router.get("tf_6_1_1projecttimeframe", response=list[schema_out.Tf_6_1_1ProjecttimeframeSchema], exclude_none=True)
def tf_6_1_1projecttimeframe(request):
    queryset = models.Tf_6_1_1Projecttimeframe.objects.all()
    return queryset


@router.get("tf_6_1_1projectdetails", response=list[schema_out.Tf_6_1_1ProjectdetailsSchema], exclude_none=True)
def tf_6_1_1projectdetails(request):
    queryset = models.Tf_6_1_1Projectdetails.objects.all()
    return queryset


@router.get(
    "tf_6_1_1projectbeneficiaries", response=list[schema_out.Tf_6_1_1ProjectbeneficiariesSchema], exclude_none=True
)
def tf_6_1_1projectbeneficiaries(request):
    queryset = models.Tf_6_1_1Projectbeneficiaries.objects.all()
    return queryset


@router.get(
    "tf_6_1_1projectoutputrepeaterprojectoutput",
    response=list[schema_out.Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema],
    exclude_none=True,
)
def tf_6_1_1projectoutputrepeaterprojectoutput(request):
    queryset = models.Tf_6_1_1ProjectoutputRepeaterprojectoutput.objects.all()
    return queryset


@router.get("tf_6_1_1projectoutput", response=list[schema_out.Tf_6_1_1ProjectoutputSchema], exclude_none=True)
def tf_6_1_1projectoutput(request):
    queryset = models.Tf_6_1_1Projectoutput.objects.all()
    queryset = queryset.prefetch_related(
        "repeaterProjectOutput",
    )
    return queryset


@router.get(
    "tf_6_1_1projectoutputrepeaterprojectoutput",
    response=list[schema_out.Tf_6_1_1ProjectoutputRepeaterprojectoutputSchema],
    exclude_none=True,
)
def tf_6_1_1projectoutputrepeaterprojectoutput(request):
    queryset = models.Tf_6_1_1ProjectoutputRepeaterprojectoutput.objects.all()
    return queryset
