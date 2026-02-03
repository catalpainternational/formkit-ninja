from .personalinfo import personalinfo, create_personalinfo  # noqa: F401

from ninja import Router

router = Router(tags=["forms"])
from .personalinfo import router as personalinfo_router

router.add_router("", personalinfo_router)

__all__ = ["router", "personalinfo", "create_personalinfo"]
