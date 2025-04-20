import json
import logging
import os
import secrets
import uuid
import webbrowser
from datetime import datetime
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from fastapi import Depends
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.services import create_or_update_account, create_session, find_or_create_user

logger = logging.getLogger("fastapi")

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")

# Store states to prevent CSRF
active_states = {}


def create_oauth_flow() -> Flow:
    """Create a Google OAuth flow."""
    # Configure the OAuth client
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

    # Create flow instance
    flow = Flow.from_client_config(
        client_config,
        scopes=[
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid",
        ],
        redirect_uri=REDIRECT_URI,
    )

    return flow


def generate_auth_url() -> Tuple[str, str]:
    """Generate authorization URL and state for Google OAuth."""
    flow = create_oauth_flow()

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(16)
    active_states[state] = True

    # Generate authorization URL
    auth_url = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )[0]

    return auth_url, state


def exchange_code_for_token(
    code: str,
    state: str,
    db: Optional[Session] = None,
    request_info: Optional[Dict] = None,
) -> Optional[Dict]:
    """Exchange authorization code for tokens and save user data."""
    # Verify state to prevent CSRF
    if state not in active_states:
        return None

    # Clean up used state
    del active_states[state]

    # Create flow and fetch token
    flow = create_oauth_flow()
    flow.fetch_token(code=code)

    # Get credentials and convert to dict
    credentials = flow.credentials
    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expires_in": credentials.expiry.timestamp(),
    }

    # Get user info
    user_info = get_user_info(credentials.token)
    if user_info:
        token_data["user_info"] = user_info

        # Save to database if db session is provided
        if db and user_info.get("email"):
            try:
                # Find or create user
                user, is_new = find_or_create_user(db, user_info)
                logger.info(
                    f"{'new user registered' if is_new else 'user logged in'}"
                )

                # Create or update account
                account = create_or_update_account(
                    db=db, user_id=user.id, provider_id="google", token_data=token_data
                )

                # Create session if request info is provided
                if request_info:
                    session = create_session(
                        db=db,
                        user_id=user.id,
                        ip_address=request_info.get("ip"),
                        user_agent=request_info.get("user_agent"),
                    )
                    token_data["session_token"] = session.token

                # Add user ID to token data
                token_data["user_id"] = user.id

                logger.info(f"user ID: {user.id}")
                logger.info(f"account ID: {account.id}")
            except Exception as e:
                logger.error(f"database operation error")
                logger.error(f"error type: {type(e).__name__}")
                logger.error(f"error details: {str(e)}")

    return token_data


def get_user_info(access_token: str) -> Optional[Dict]:
    """Get user information using the access token."""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = httpx.get(
            "https://www.googleapis.com/oauth2/v1/userinfo", headers=headers
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"get_user_info error: {e}")
        return None
