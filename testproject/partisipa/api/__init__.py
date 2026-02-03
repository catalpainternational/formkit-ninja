"""Partisipa API package."""

from ninja import Router

from .tf611 import router as tf611_router

router = Router(tags=["partisipa"])


# Health check endpoint
@router.get("health", response=dict)
def health_check(request):
    """Health check endpoint for partisipa app."""
    return {"status": "ok", "app": "partisipa"}


# Merge TF611 router
router.add_router("", tf611_router)

__all__ = ["router"]
