"""Reusable RBAC dependencies for FastAPI routes."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status, Request

from ..models import User
from .security import get_current_user, normalize_role


def require_roles(*allowed_roles: str) -> Callable[[User], User]:
	"""Return a FastAPI dependency that enforces one of the allowed roles."""

	allowed = {normalize_role(role) for role in allowed_roles if role}

	def dependency(current_user: User = Depends(get_current_user)) -> User:
		user_role = normalize_role(current_user.role)
		if user_role not in allowed:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="Insufficient permissions",
			)
		return current_user

	return dependency
