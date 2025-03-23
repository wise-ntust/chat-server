import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

DATABASE_URL = os.getenv("POSTGRESQL_URL")

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base for models
Base = declarative_base()


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Generate UUID for IDs
def generate_uuid():
    return str(uuid.uuid4())


# Base timestamp fields
class TimestampMixin:
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updatedAt = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# User model
class User(Base, TimestampMixin):
    __tablename__ = "user"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True)
    emailVerified = Column(Boolean, default=False)
    image = Column(String, nullable=True)

    # Relationships
    account = relationship(
        "Account", back_populates="user", cascade="all, delete-orphan"
    )
    session = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )


# Account model
class Account(Base, TimestampMixin):
    __tablename__ = "account"

    id = Column(String, primary_key=True, default=generate_uuid)
    accountId = Column(String, nullable=True)
    providerId = Column(String, nullable=False)
    userId = Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    accessToken = Column(String, nullable=True)
    refreshToken = Column(String, nullable=True)
    idToken = Column(String, nullable=True)
    accessTokenExpiresAt = Column(DateTime, nullable=True)
    refreshTokenExpiresAt = Column(DateTime, nullable=True)
    scope = Column(String, nullable=True)
    password = Column(String, nullable=True)

    # Relationships
    user = relationship("User", back_populates="account")


# Session model
class Session(Base, TimestampMixin):
    __tablename__ = "session"

    id = Column(String, primary_key=True, default=generate_uuid)
    expiresAt = Column(DateTime, nullable=False)
    token = Column(String, nullable=False, unique=True)
    ipAddress = Column(String, nullable=True)
    userAgent = Column(String, nullable=True)
    userId = Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    user = relationship("User", back_populates="session")


# Create all tables
def init_db():
    Base.metadata.create_all(bind=engine)
