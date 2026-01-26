"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from ninja import Router

from . import models, schema_out

router = Router(tags=["forms"])


@router.get("testgroup", response=list[schema_out.TestgroupSchema], exclude_none=True)
def testgroup(request):
    queryset = models.Testgroup.objects.all()
    return queryset
