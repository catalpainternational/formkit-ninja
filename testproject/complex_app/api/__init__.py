from ninja import Router

from .mainform import create_mainform, create_mainformlineitems, mainform, mainformlineitems  # noqa: F401
from .mainform import router as mainform_router

router = Router(tags=["forms"])
router.add_router("", mainform_router)

__all__ = ["router", "mainform", "create_mainform", "mainformlineitems", "create_mainformlineitems"]
