import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Account
from .database import Session as DbSession
from .database import User


def find_or_create_user(db: Session, user_info: Dict) -> Tuple[User, bool]:
    """
    Find an existing user by email or create a new one.
    Returns the user and a boolean indicating if it's a new user.
    """
    email = user_info.get("email")
    if not email:
        raise ValueError("Email is required to find or create a user")

    print(f"\n=== 嘗試查詢用戶： {email} ===")

    # Try to find existing user
    user = db.query(User).filter(User.email == email).first()

    if user:
        print(f"找到現有用戶: ID = {user.id}, Email = {user.email}")
    else:
        print(f"未找到用戶，將創建新用戶")

    is_new_user = False

    # Create new user if not exists
    if not user:
        is_new_user = True
        user = User(
            id=str(uuid.uuid4()),
            name=user_info.get("name"),
            email=email,
            emailVerified=user_info.get("verified_email", False),
            image=user_info.get("picture"),
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            # Try one more time in case of race condition
            user = db.query(User).filter(User.email == email).first()
            if not user:
                raise
            is_new_user = False

    return user, is_new_user


def create_or_update_account(
    db: Session, user_id: str, provider_id: str, token_data: Dict
) -> Account:
    """
    Create or update an OAuth account for a user.
    """
    # Look for existing account
    account = (
        db.query(Account)
        .filter(Account.userId == user_id, Account.providerId == provider_id)
        .first()
    )

    # Calculate expiry times if available
    access_expires = None
    if token_data.get("expires_in"):
        # 修復：檢查是否為 datetime 對象並適當處理
        expires_in = token_data.get("expires_in")
        if isinstance(expires_in, datetime):
            access_expires = expires_in  # 直接使用 datetime 對象
        else:
            try:
                # 原始邏輯，嘗試轉換為秒數
                access_expires = datetime.now(timezone.utc) + timedelta(
                    seconds=int(expires_in)
                )
            except (TypeError, ValueError) as e:
                print(f"無法處理 expires_in 值: {expires_in}, 錯誤: {str(e)}")
                # 設置一個預設過期時間，例如 1 小時後
                access_expires = datetime.now(timezone.utc) + timedelta(hours=1)

    refresh_expires = None
    if token_data.get("refresh_token_expires_in"):
        refresh_expires = datetime.now(timezone.utc) + timedelta(
            seconds=int(token_data.get("refresh_token_expires_in"))
        )

    # Process scope
    scope = None
    if isinstance(token_data.get("scopes"), list):
        scope = " ".join(token_data.get("scopes"))

    # 獲取 Google ID 作為 accountId
    google_id = None
    if provider_id == "google" and token_data.get("user_info"):
        user_info = token_data.get("user_info")
        google_id = user_info.get("id")

    # 如果沒有找到 Google ID，使用備用方案
    account_id = google_id or f"{provider_id}_{user_id}"

    # Create or update account
    if not account:
        account = Account(
            userId=user_id,
            providerId=provider_id,
            accountId=account_id,  # 使用 Google ID 或備用值
            accessToken=token_data.get("token"),
            refreshToken=token_data.get("refresh_token"),
            idToken=token_data.get("id_token"),
            accessTokenExpiresAt=access_expires,
            refreshTokenExpiresAt=refresh_expires,
            scope=scope,
        )
        db.add(account)
    else:
        # Update existing account
        if not account.accountId and account_id:
            account.accountId = account_id  # 如果之前沒有設置 accountId，現在設置

        account.accessToken = token_data.get("token")
        if token_data.get("refresh_token"):  # Only update if present
            account.refreshToken = token_data.get("refresh_token")
        if token_data.get("id_token"):
            account.idToken = token_data.get("id_token")
        account.accessTokenExpiresAt = access_expires
        account.refreshTokenExpiresAt = refresh_expires
        if scope:
            account.scope = scope
        account.updatedAt = datetime.now(timezone.utc)

    db.commit()
    db.refresh(account)
    return account


def create_session(
    db: Session,
    user_id: str,
    token: str = None,
    ip_address: str = None,
    user_agent: str = None,
    expires_in: int = 30,  # Default 30 days
) -> DbSession:
    """
    Create a new session for a user.
    """
    if not token:
        token = str(uuid.uuid4())

    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in)

    session = DbSession(
        userId=user_id,
        token=token,
        expiresAt=expires_at,
        ipAddress=ip_address,
        userAgent=user_agent,
    )

    db.add(session)
    db.commit()
    db.refresh(session)
    return session

    return session

    return session

    return session


def find_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Find a user by their ID."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_id_from_session(db: Session, session_token: str) -> Optional[str]:
    """Get user ID from session token."""
    session = (
        db.query(DbSession)
        .filter(
            DbSession.token == session_token,
            DbSession.expiresAt > datetime.now(timezone.utc),
        )
        .first()
    )

    if not session:
        return None

    return session.userId
