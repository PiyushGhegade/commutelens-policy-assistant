import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings

COMPANIES = {"atlas": "Atlas Labs", "beacon": "Beacon Works", "cedar": "Cedar Systems"}
# This is a mock employee directory, not a production identity provider.
USERS = {
    "asha": ("atlas", "employee"),
    "bilal": ("beacon", "employee"),
    "chitra": ("cedar", "employee"),
    "atlas-admin": ("atlas", "admin"),
    "beacon-admin": ("beacon", "admin"),
    "cedar-admin": ("cedar", "admin"),
}
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    subject: str
    company: str
    role: str


def issue(settings: Settings, username: str, password: str) -> str:
    if not settings.demo_mode:
        raise HTTPException(404, "Demo login is disabled.")
    if username not in USERS or not hmac.compare_digest(password, settings.demo_password):
        raise HTTPException(401, "Invalid demo credentials.")
    company, role = USERS[username]
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": username,
            "company": company,
            "role": role,
            "iss": "commute-demo",
            "aud": "commute-policy",
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def identity(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> Identity:
    if credentials is None:
        raise HTTPException(401, "Sign in to ask about your company policy.")
    try:
        claims = jwt.decode(
            credentials.credentials,
            request.app.state.settings.jwt_secret,
            algorithms=["HS256"],
            audience="commute-policy",
            issuer="commute-demo",
            options={"require": ["sub", "company", "role", "exp", "iat", "aud", "iss"]},
        )
        if claims["company"] not in COMPANIES or claims["role"] not in {"employee", "admin"}:
            raise ValueError("Unknown scope")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("Invalid subject")
        return Identity(claims["sub"], claims["company"], claims["role"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, "Your session is invalid or expired. Sign in again.") from None


def admin(user: Identity = Depends(identity)) -> Identity:
    if user.role != "admin":
        raise HTTPException(403, "Only your company's policy administrator can publish policies.")
    return user
