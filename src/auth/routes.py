import json
import logging
import os
import uuid
import webbrowser
from typing import Dict, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db.database import get_db, init_db
from .oauth import exchange_code_for_token, generate_auth_url

logger = logging.getLogger("fastapi")

router = APIRouter(prefix="/auth", tags=["authentication"])

client_token_storage = {}

pending_clients = {}

init_db()


@router.get("/login")
async def login():
    """
    Initiate OAuth login flow.

    If client_id is provided, this is a CLI client request.
    Returns a URL that the client should open in a browser.

    If auto_open is True, automatically opens the browser.
    """
    auth_url, state = generate_auth_url()

    client_id = str(uuid.uuid4())

    pending_clients[state] = client_id

    return {"auth_url": auth_url, "state": state, "client_id": client_id}


@router.get("/callback")
async def oauth_callback(
    request: Request, code: str, state: str, db: Session = Depends(get_db)
):
    """
    Handle the OAuth callback from Google.

    After successful authentication, Google redirects here.
    """
    request_info = {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }

    token_data = exchange_code_for_token(code, state, db, request_info)

    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if "user_info" in token_data:
        user_info = token_data["user_info"]
        logger.info(f"user_info: {user_info}")
    else:
        logger.info("授權成功，但無法獲取用戶資訊")

    if state in pending_clients:
        client_id = pending_clients[state]
        client_token_storage[client_id] = token_data
        html_content = """
        <html>
          <body style="font-family: monospace; background-color: #000; color: #fff; width: 100dvw; height: 100dvh; display: flex; flex-direction: column; justify-content: center; align-items: center;">
            <h1>Authentication successful.</h1>
            <p>You can now close this window and return to the CLI application!</p>
          </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    return token_data


@router.get("/token/{client_id}")
async def get_token(client_id: str):
    """
    Endpoint for CLI clients to retrieve their token after OAuth flow.
    The CLI client should poll this endpoint until the token is available.
    """
    if client_id in client_token_storage:
        token_data = client_token_storage[client_id].copy()
        del client_token_storage[client_id]
        return token_data

    return {"status": "pending"}
