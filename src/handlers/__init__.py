from .start import router as start_router
from .buy import router as buy_router
from .profile import router as profile_router
from .admin import router as admin_router

__all__ = ["start_router", "buy_router", "profile_router", "admin_router"]
