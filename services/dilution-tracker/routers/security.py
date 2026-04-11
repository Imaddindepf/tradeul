"""
Security helpers for sensitive dilution endpoints.
"""

from fastapi import Header, HTTPException

ALLOWED_DILUTION_ADMIN_EMAIL = "peertopeerhack@gmail.com"
ALLOWED_DILUTION_ADMIN_USER_ID = "user_35yNHnXvRwQw22DDb0M5zEKcWsX"


def require_dilution_admin_email(
    x_user_email: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> str:
    email_match = (x_user_email or "").strip().lower() == ALLOWED_DILUTION_ADMIN_EMAIL
    user_id_match = (x_user_id or "").strip() == ALLOWED_DILUTION_ADMIN_USER_ID
    if not email_match and not user_id_match:
        raise HTTPException(
            status_code=403,
            detail="Only the dilution admin can modify dilution data",
        )
    return (x_user_email or "").strip().lower()
