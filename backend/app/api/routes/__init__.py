from .alerts import router as alerts_router
from .analytics import router as analytics_router
from .auth import router as auth_router
from .cameras import router as cameras_router
from .jobs import router as jobs_router
from .media import router as media_router
from .monitoring import router as monitoring_router
from .incidents import router as incidents_router
from .users import router as users_router

__all__ = [
	"alerts_router",
	"analytics_router",
	"auth_router",
	"cameras_router",
	"jobs_router",
	"media_router",
	"monitoring_router",
	"incidents_router",
	"users_router",
]
