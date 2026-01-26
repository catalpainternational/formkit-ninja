"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from ninja import Router

from . import models, schema_out

router = Router(tags=["forms"])


@router.get("parentitems", response=list[schema_out.ParentItemsSchema], exclude_none=True)
def parentitems(request):
    queryset = models.ParentItems.objects.all()
    return queryset


@router.get("parentchild", response=list[schema_out.ParentChildSchema], exclude_none=True)
def parentchild(request):
    queryset = models.ParentChild.objects.all()
    return queryset


@router.get("parent", response=list[schema_out.ParentSchema], exclude_none=True)
def parent(request):
    queryset = models.Parent.objects.all()
    queryset = queryset.select_related(
        "child",
    )
    queryset = queryset.prefetch_related(
        "items",
    )
    return queryset


@router.get("parentchild", response=list[schema_out.ParentChildSchema], exclude_none=True)
def parentchild(request):
    queryset = models.ParentChild.objects.all()
    return queryset


@router.get("parentitems", response=list[schema_out.ParentItemsSchema], exclude_none=True)
def parentitems(request):
    queryset = models.ParentItems.objects.all()
    return queryset
