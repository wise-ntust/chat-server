import datetime
import os
from typing import List

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import PyMongoError

router = APIRouter(prefix="/chat", tags=["chat"])

mongo_client = MongoClient(os.getenv("MONGODB_URL"))
db = mongo_client["chat"]
chatrooms_collection = db["chatrooms"]
messages_collection = db["messages"]


class MessageCreate(BaseModel):
    chatroom_id: str
    sender_id: str
    content: str


class MessageResponse(BaseModel):
    id: str
    chatroom_id: str
    sender_id: str
    content: str
    sent_at: datetime.datetime


def serialize_object_id(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize_object_id(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_object_id(item) for item in obj]
    return obj


@router.post("/messages", response_model=MessageResponse)
async def send_message(request: MessageCreate):
    """Send message to chatroom"""
    try:
        if not ObjectId.is_valid(request.chatroom_id):
            raise HTTPException(status_code=400, detail="Invalid chatroom ID format")

        chatroom = chatrooms_collection.find_one({"_id": ObjectId(request.chatroom_id)})
        if not chatroom:
            raise HTTPException(status_code=404, detail="Chatroom not found")

        if request.sender_id not in chatroom["participants"]:
            raise HTTPException(
                status_code=403, detail="Sender is not a member of the chatroom"
            )

        now = datetime.datetime.utcnow()
        message = {
            "chatroom_id": request.chatroom_id,
            "sender_id": request.sender_id,
            "content": request.content,
            "sent_at": now,
        }

        result = messages_collection.insert_one(message)
        message_id = result.inserted_id

        chatrooms_collection.update_one(
            {"_id": ObjectId(request.chatroom_id)}, {"$set": {"updated_at": now}}
        )

        created_message = messages_collection.find_one({"_id": message_id})
        if not created_message:
            raise HTTPException(
                status_code=500, detail="Failed to retrieve created message"
            )
        created_message["id"] = str(created_message.pop("_id"))

        return created_message

    except HTTPException:
        raise

    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/chatrooms/{chatroom_id}/messages")
async def get_messages(chatroom_id: str, user_id: str, limit: int = 50, skip: int = 0):
    """Get messages from chatroom"""
    try:
        if not ObjectId.is_valid(chatroom_id):
            raise HTTPException(status_code=400, detail="Invalid chatroom ID format")

        try:
            chatroom = chatrooms_collection.find_one({"_id": ObjectId(chatroom_id)})
        except Exception as e:
            chatroom = None

        if not chatroom:
            raise HTTPException(status_code=404, detail="Chatroom not found")

        if user_id not in chatroom["participants"]:
            raise HTTPException(
                status_code=403, detail="User is not a member of the chatroom"
            )

        try:
            messages_cursor = (
                messages_collection.find({"chatroom_id": chatroom_id})
                .sort("sent_at", -1)
                .skip(skip)
                .limit(limit)
            )
            messages = []
            for msg in messages_cursor:
                msg["id"] = str(msg.pop("_id"))
                messages.append(msg)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to query messages: {str(e)}"
            )

        return {"messages": serialize_object_id(messages)}

    except HTTPException:
        raise

    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
