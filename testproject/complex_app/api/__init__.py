from .mainform import mainform, create_mainform, mainformlineitems, create_mainformlineitems  # noqa: F401

from ninja import Router

router = Router(tags=["forms"])
from .mainform import router as mainform_router

router.add_router("", mainform_router)

__all__ = ["router", "mainform", "create_mainform", "mainformlineitems", "create_mainformlineitems"]
