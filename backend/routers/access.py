"""The portal's access key: the gate before everything (status, unlock), and the admin's page to set it."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from backend.config import COOKIE_SECURE
from backend.models.entities import PlatformAdmin
from backend.services import access_key, audit, login_limits
from backend.services.auth_service import require_app_admin

router = APIRouter(tags=["Access key"])


class KeyRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)


@router.get("/access/status")
def access_status(request: Request):
    """Whether this browser must enter the portal's access key first (no key set: open)."""
    return {"required": access_key.is_set(), "granted": access_key.unlocked(request.cookies.get(access_key.COOKIE))}


@router.post("/access/unlock")
def access_unlock(payload: KeyRequest, request: Request, response: Response):
    address = request.client.host if request.client else None
    who = f"access-key:{address or 'unknown'}"                 # wrong guesses slow down this browser, not everyone
    wait = login_limits.check(who, address)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait)},
                            detail=f"Too many wrong keys. Please try again in {wait} second{'s' if wait != 1 else ''}.")
    if not access_key.check(payload.key):
        login_limits.failed(who, address)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That is not the portal's access key. Ask your admin for it.")
    login_limits.succeeded(who)
    response.set_cookie(access_key.COOKIE, access_key.cookie_value(), max_age=access_key.DAYS * 86400, httponly=True,
                        secure=COOKIE_SECURE, samesite="lax", path="/api")
    return {"granted": True}


@router.get("/platform/access-key")
def access_key_status(admin: PlatformAdmin = Depends(require_app_admin)):
    return access_key.status()


@router.put("/platform/access-key")
def access_key_set(payload: KeyRequest, response: Response, admin: PlatformAdmin = Depends(require_app_admin)):
    """Sets or changes the key. Everyone (the admin too) enters the new key next time; this browser stays unlocked."""
    try:
        version = access_key.set_key(payload.key)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    response.set_cookie(access_key.COOKIE, access_key.cookie_value(), max_age=access_key.DAYS * 86400, httponly=True,
                        secure=COOKIE_SECURE, samesite="lax", path="/api")
    audit.record(f"app_admin:{admin.id}", "access_key_set", "platform", admin.id, None, {"version": version})   # never the key
    return access_key.status()


@router.delete("/platform/access-key")
def access_key_clear(admin: PlatformAdmin = Depends(require_app_admin)):
    access_key.clear()
    audit.record(f"app_admin:{admin.id}", "access_key_cleared", "platform", admin.id)
    return access_key.status()
