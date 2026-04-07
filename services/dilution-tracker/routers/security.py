"""
Security helpers for sensitive dilution endpoints.
"""

from fastapi import Header, HTTPException

ALLOWED_DILUTION_ADMIN_EMAIL = "peertopeerhack@gmail.com"


def require_dilution_admin_email(x_user_email: str | None = Header(default=None)) -> str:
    email = (x_user_email or "").strip().lower()
    if email != ALLOWED_DILUTION_ADMIN_EMAIL:
        raise HTTPException(
            status_code=403,
            detail="Only the dilution admin can modify dilution data",
        )
    return email
