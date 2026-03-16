"""Auth dependencies for FastAPI: session user, namespace, role-based access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import settings


def _get_db(request: Request):
    """Get database from app state. Returns None if DATABASE_URL not set."""
    return getattr(request.app.state, "db", None)


def get_user_namespace(username: str, user_id: int) -> str:
    """Build Kubernetes namespace for user: {prefix}-{username_safe}-{user_id}.
    Username underscores are replaced with hyphens (K8s namespace allows only a-z, 0-9, -).
    """
    prefix = settings.K8S_NAMESPACE_PREFIX or "kv"
    ns_safe = username.lower().replace("_", "-")
    namespace = f"{prefix}-{ns_safe}-{user_id}"
    if not namespace[0].isalpha():
        raise ValueError(
            "Namespace must start with a letter. Check K8S_NAMESPACE_PREFIX and username."
        )
    return namespace


@dataclass
class SessionUser:
    """Current user from session."""

    user_id: int
    username: str
    role: str
    namespace: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def get_current_user(request: Request) -> SessionUser:
    """Extract authenticated user from session."""
    session = request.session
    username = session.get("username")
    user_id = session.get("user_id")
    role = session.get("role", "user")

    if not username or user_id is None:
        if "/api/" in request.url.path or "/vms" in request.url.path:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return RedirectResponse(url="/login", status_code=303)

    try:
        namespace = session.get("namespace") or get_user_namespace(username, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if namespace and not namespace[0].isalpha():
        raise HTTPException(
            status_code=400,
            detail="Namespace must start with a letter. Re-login or fix K8S_NAMESPACE_PREFIX.",
        )
    return SessionUser(user_id=user_id, username=username, role=role, namespace=namespace)


async def get_current_namespace(
    user: Annotated[SessionUser, Depends(get_current_user)],
) -> str:
    """Current user's Kubernetes namespace."""
    return user.namespace


async def require_owner(
    request: Request,
    username: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
) -> SessionUser:
    """Require that path username matches session user."""
    if user.username == username:
        return user
    raise HTTPException(status_code=403, detail="Access denied")


async def require_admin(
    user: Annotated[SessionUser, Depends(get_current_user)],
) -> SessionUser:
    """Require admin role."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
