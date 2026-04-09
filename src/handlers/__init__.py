from .start import router as start_router
from .buy import router as buy_router
from .profile import router as profile_router
from .admin import router as admin_router
from .admin_panel import router as admin_panel_router
from .support import router as support_router
from .referral import router as referral_router
from .gift_friend import router as gift_friend_router

__all__ = [
    "start_router",
    "buy_router",
    "profile_router",
    "admin_router",
    "admin_panel_router",
    "support_router",
    "referral_router",
    "gift_friend_router",
]
