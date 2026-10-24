"""Password hashing (bcrypt, used directly) and JWT tokens (HS256).

- bcrypt has a 72-byte password limit; request schemas reject longer
  passwords with a clear message (see schemas.py).
- Tokens carry only user id and role. Every request reloads the user from
  the database, so a deactivated account is locked out immediately.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. The salt is inside the result."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plain password against a stored bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, user_id: int, role: str, secret: str, expires_minutes: int) -> str:
    """Make a signed JWT. Payload: sub (user id) and role only."""
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(UTC) + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict:
    """Verify and decode a JWT. Raises jwt.PyJWTError when bad or expired."""
    return jwt.decode(token, secret, algorithms=[ALGORITHM])
