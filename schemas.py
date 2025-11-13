"""
Database Schemas for Purebred Pet Matchmaking App

Each Pydantic model represents a MongoDB collection (collection name is the lowercase of the class name).
"""
from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal

# ========== Core Schemas ==========

class Owner(BaseModel):
    name: str = Field(..., description="Owner full name")
    email: EmailStr = Field(..., description="Unique owner email")
    city: Optional[str] = Field(None, description="City or locality")
    location_lat: Optional[float] = Field(None, ge=-90, le=90)
    location_lng: Optional[float] = Field(None, ge=-180, le=180)
    premium: bool = Field(False, description="Premium subscription status")
    verified: bool = Field(False, description="Whether owner has verified identity")

class Pet(BaseModel):
    owner_id: str = Field(..., description="Owner document id")
    species: Literal['dog', 'cat'] = Field(..., description="Pet species")
    name: str
    breed: str
    age: int = Field(..., ge=0, le=35)
    gender: Literal['male', 'female']
    pedigree: bool = Field(False, description="Has pedigree documents")
    photos: List[str] = Field(default_factory=list, description="Image URLs")
    videos: List[str] = Field(default_factory=list, description="Video URLs")
    personality: List[str] = Field(default_factory=list, description="Traits e.g. playful, calm")
    preferences: List[str] = Field(default_factory=list, description="Preferences e.g. social, quiet")
    city: Optional[str] = None
    location_lat: Optional[float] = Field(None, ge=-90, le=90)
    location_lng: Optional[float] = Field(None, ge=-180, le=180)
    verified: bool = Field(False, description="Profile verified via photo/pedigree")

class Like(BaseModel):
    liker_pet_id: str
    target_pet_id: str
    action: Literal['like', 'pass']
    created_by_owner_id: str

class Match(BaseModel):
    pet_a_id: str
    pet_b_id: str
    owner_a_id: str
    owner_b_id: str

class Message(BaseModel):
    match_id: str
    sender_pet_id: str
    sender_owner_id: str
    text: str

class Announcement(BaseModel):
    owner_id: str
    pet_id: Optional[str] = None
    species: Literal['dog', 'cat']
    title: str
    description: str
    city: Optional[str] = None
    date: Optional[str] = Field(None, description="ISO date for event if applicable")
    type: Literal['breeding', 'event']

class Verification(BaseModel):
    pet_id: str
    type: Literal['photo', 'pedigree']
    status: Literal['pending', 'approved', 'rejected'] = 'pending'
    document_url: Optional[str] = None

# The Flames database viewer can read these models via the /schema endpoint in main.py.
