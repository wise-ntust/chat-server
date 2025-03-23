import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_user_id
from ..db.database import get_db

logger = logging.getLogger("fastapi")


router = APIRouter(prefix="/friends", tags=["friends"])


class Friend(BaseModel):
    id: str
    name: str
    email: str
    requestId: Optional[str] = None
    chatroom_id: Optional[str] = None


class FriendActionRequest(BaseModel):
    friendId: str


@router.get("/")
async def get_friends(
    user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Get user's friends list"""
    try:
        query = text(
            """
            SELECT u.id, u.name, u.email, uf.chatroom_id
            FROM "user" u
            JOIN user_friends uf ON u.id = uf.friend_id
            WHERE uf.user_id = :userId AND uf.status = 'accepted'
            """
        )
        result = db.execute(query, {"userId": user_id})
        friends = [
            {"id": row[0], "name": row[1], "email": row[2], "chatroom_id": row[3]}
            for row in result.fetchall()
        ]

        return friends

    except Exception as e:
        logger.error(f"get_friends error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get friends list")


@router.post("/")
async def send_friend_request(
    friend_email: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Send friend request"""
    try:
        # Check if friend exists
        user_query = text(
            """
            SELECT id FROM "user" WHERE email = :email
            """
        )
        result = db.execute(user_query, {"email": friend_email})
        user = result.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        friend_id = user[0]

        # Check if trying to add yourself as a friend
        if user_id == friend_id:
            raise HTTPException(
                status_code=400, detail="Cannot add yourself as a friend"
            )

        # Check if already a friend
        friendship_query = text(
            """
            SELECT * FROM user_friends
            WHERE (user_id = :userId AND friend_id = :friendId) OR
                  (user_id = :friendId AND friend_id = :userId)
            """
        )
        result = db.execute(
            friendship_query, {"userId": user_id, "friendId": friend_id}
        )
        existing_friendship = result.fetchone()

        if existing_friendship:
            status = existing_friendship[3]  # Assuming status is the fourth column
            if status == "accepted":
                raise HTTPException(status_code=400, detail="Already a friend")
            elif status == "pending":
                raise HTTPException(
                    status_code=400, detail="Friend request already sent"
                )

        # Send friend request
        send_request_query = text(
            """
            SELECT send_friend_request(:userId, :friendId)
            """
        )
        db.execute(send_request_query, {"userId": user_id, "friendId": friend_id})
        db.commit()

        return {"message": "Friend request sent"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"send_friend_request error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to send friend request")


@router.get("/requests")
async def get_friend_requests(
    user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Get user's friend requests list"""
    try:
        query = text(
            """
            SELECT u.id, u.name, u.email, uf.id as request_id
            FROM "user" u
            JOIN user_friends uf ON u.id = uf.user_id
            WHERE uf.friend_id = :userId AND uf.status = 'pending'
            """
        )
        result = db.execute(query, {"userId": user_id})

        friend_requests = [
            {"id": row[0], "name": row[1], "email": row[2], "requestId": row[3]}
            for row in result.fetchall()
        ]

        return friend_requests

    except Exception as e:
        logger.error(f"get_friend_requests error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get friend requests")


def create_chatroom(user_id: str, friend_id: str) -> str:
    try:
        import os

        from pymongo import MongoClient

        mongo_client = MongoClient(os.getenv("MONGODB_URL"))

        chat_db = mongo_client["chat"]
        chatrooms_collection = chat_db["chatrooms"]

        chatroom = {
            "name": f"{user_id}, {friend_id}",
            "creator_id": user_id,
            "participants": [user_id, friend_id],
        }

        result = chatrooms_collection.insert_one(chatroom)
        chatroom_id = str(result.inserted_id)

        return chatroom_id

    except Exception as e:

        return None


@router.post("/accept")
async def accept_friend_request(
    friend_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Accept friend request"""

    try:
        if not friend_id:
            raise HTTPException(status_code=400, detail="Missing required parameters")

        check_query = text(
            """
            SELECT EXISTS (
                SELECT 1 FROM user_friends
                WHERE user_id = :sender_id AND friend_id = :receiver_id AND status = 'pending'
            )
            """
        )
        result = db.execute(
            check_query,
            {
                "sender_id": friend_id,
                "receiver_id": user_id,
            },
        )
        request_exists = result.fetchone()[0]

        if not request_exists:
            raise HTTPException(status_code=404, detail="Friend request not found")

        chatroom_id = create_chatroom(user_id, friend_id)

        query = text(
            """
            SELECT accept_friend_request(:p_user_id, :p_friend_id, :p_chatroom_id)
            """
        )
        result = db.execute(
            query,
            {
                "p_user_id": user_id,
                "p_friend_id": friend_id,
                "p_chatroom_id": chatroom_id,
            },
        )
        accepted = result.fetchone()[0]

        logger.info(f"accepted: {accepted}")

        if not accepted:
            raise HTTPException(status_code=404, detail="Friend request not found")

        db.commit()
        return {"message": "Friend request accepted", "chatroom_id": chatroom_id}

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to accept friend request")


@router.post("/reject")
async def reject_friend_request(
    friend_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Reject friend request"""
    try:
        if not friend_id:
            raise HTTPException(status_code=400, detail="Missing required parameters")

        query = text(
            """
            SELECT reject_friend_request(:userId, :friendId)
            """
        )
        result = db.execute(query, {"userId": user_id, "friendId": friend_id})
        rejected = result.fetchone()[0]

        if not rejected:
            raise HTTPException(status_code=404, detail="Friend request not found")

        db.commit()
        return {"message": "Friend request rejected"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"reject_friend_request error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reject friend request")


@router.post("/delete")
async def delete_friend(
    friend_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Delete friend relationship"""
    try:
        if not friend_id:
            raise HTTPException(status_code=400, detail="Missing required parameters")

        if friend_id == user_id:
            raise HTTPException(status_code=403, detail="Cannot delete yourself")

        query = text(
            """
            SELECT remove_friend(:userId, :friendId)
        """
        )
        result = db.execute(query, {"userId": user_id, "friendId": friend_id})
        removed = result.fetchone()[0]

        if not removed:
            raise HTTPException(status_code=404, detail="Friend relationship not found")

        db.commit()
        return {"message": "Friend deleted"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"delete_friend error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete friend")
