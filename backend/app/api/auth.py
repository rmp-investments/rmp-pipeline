"""
Authentication API endpoints.

MVP implementation uses HTTP Basic Auth.
TODO: Upgrade to JWT token-based auth for production.
"""

from typing import Optional
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.config import settings


router = APIRouter()
security = HTTPBasic()


# ----- Pydantic Schemas -----


class UserResponse(BaseModel):
    """Response schema for current user info."""

    username: str
    role: str


class LoginResponse(BaseModel):
    """Response schema for login endpoint."""

    status: str
    username: str
    message: str


# ----- Authentication Functions -----


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Verify HTTP Basic Auth credentials.

    MVP implementation - uses credentials from config.
    TODO: Replace with database lookup for production.
    """
    # Use secrets.compare_digest to prevent timing attacks
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"),
        settings.basic_auth_username.encode("utf8"),
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        settings.basic_auth_password.encode("utf8"),
    )

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


def get_current_user(username: str = Depends(verify_credentials)) -> dict:
    """
    Get the current authenticated user.

    MVP implementation - returns basic user info.
    TODO: Return full User model from database for production.
    """
    return {
        "username": username,
        "role": "admin",  # MVP: single admin role
    }


# ----- Optional Authentication -----


def optional_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> Optional[str]:
    """
    Optional authentication - returns username if provided, None otherwise.

    Useful for endpoints that have different behavior for authenticated users.
    """
    if credentials is None:
        return None

    try:
        return verify_credentials(credentials)
    except HTTPException:
        return None


# ----- API Endpoints -----


@router.post("/login", response_model=LoginResponse)
async def login(username: str = Depends(verify_credentials)):
    """
    Login endpoint - verifies credentials.

    For MVP, this just validates the credentials.
    Returns success if credentials are valid.

    In production, this would return a JWT token.
    """
    return LoginResponse(
        status="success",
        username=username,
        message="Login successful",
    )


@router.post("/logout")
async def logout():
    """
    Logout endpoint.

    For HTTP Basic Auth, this is a no-op since the browser handles caching.
    In production with JWT, this would invalidate the token.
    """
    return {"status": "success", "message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """
    Get current user information.

    Requires authentication.
    """
    return UserResponse(
        username=user["username"],
        role=user["role"],
    )


@router.get("/check")
async def check_auth(username: str = Depends(verify_credentials)):
    """
    Check if current credentials are valid.

    Returns 200 if authenticated, 401 if not.
    """
    return {"authenticated": True, "username": username}


# ----- Dependency for Protected Routes -----


def require_auth(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency to require authentication on a route.

    Usage:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(require_auth)):
            return {"message": f"Hello, {user['username']}"}
    """
    return user


# TODO: Add JWT-based authentication
# from jose import jwt, JWTError
# from datetime import datetime, timedelta
#
# def create_access_token(data: dict) -> str:
#     to_encode = data.copy()
#     expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")
#
# async def get_current_user_jwt(token: str = Depends(oauth2_scheme)):
#     try:
#         payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
#         username: str = payload.get("sub")
#         if username is None:
#             raise credentials_exception
#     except JWTError:
#         raise credentials_exception
#     # Look up user in database
#     return user

# TODO: Add user registration endpoint (for multi-user setup)
# @router.post("/register")
# async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
#     """Register a new user (admin only)."""
#     pass

# TODO: Add password change endpoint
# @router.put("/password")
# async def change_password(old_password: str, new_password: str, ...):
#     """Change user password."""
#     pass
