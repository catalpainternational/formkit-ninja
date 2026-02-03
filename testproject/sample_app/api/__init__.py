from ninja import Router

from .personalinfo import create_personalinfo, personalinfo  # noqa: F401
from .personalinfo import router as personalinfo_router

router = Router(tags=["forms"])
router.add_router("", personalinfo_router)

__all__ = ["router", "personalinfo", "create_personalinfo"]
