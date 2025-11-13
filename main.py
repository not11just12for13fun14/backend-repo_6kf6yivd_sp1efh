import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Owner, Pet, Like, Match, Message, Announcement, Verification

app = FastAPI(title="Purebred Pet Matchmaking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Helpers -----

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")

# ----- Health & Schema -----

@app.get("/")
def root():
    return {"message": "Purebred Pet Matchmaking API running"}

@app.get("/schema")
def schema():
    # Expose schema model names for the Flames DB viewer
    return {
        "collections": [
            "owner", "pet", "like", "match", "message", "announcement", "verification"
        ]
    }

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# ----- Owners -----

@app.post("/owners")
def create_owner(owner: Owner):
    existing = db["owner"].find_one({"email": owner.email}) if db else None
    if existing:
        raise HTTPException(status_code=409, detail="Owner with this email already exists")
    owner_id = create_document("owner", owner)
    return {"id": owner_id}

@app.get("/owners/{owner_id}")
def get_owner(owner_id: str):
    doc = db["owner"].find_one({"_id": oid(owner_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Owner not found")
    doc["id"] = str(doc.pop("_id"))
    return doc

# ----- Pets -----

@app.post("/pets")
def create_pet(pet: Pet):
    # ensure species is dog or cat (already via schema), and owner exists
    if not db["owner"].find_one({"_id": oid(pet.owner_id)}):
        raise HTTPException(status_code=400, detail="Owner not found")
    pet_id = create_document("pet", pet)
    return {"id": pet_id}

@app.get("/pets")
def list_pets(
    species: str = Query(..., regex="^(dog|cat)$"),
    breed: Optional[str] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    gender: Optional[str] = Query(None, regex="^(male|female)$"),
    pedigree: Optional[bool] = None,
    city: Optional[str] = None,
    owner_id: Optional[str] = None,
):
    q = {"species": species}
    if breed: q["breed"] = {"$regex": f"^{breed}$", "$options": "i"}
    if min_age is not None or max_age is not None:
        age_q = {}
        if min_age is not None: age_q["$gte"] = min_age
        if max_age is not None: age_q["$lte"] = max_age
        q["age"] = age_q
    if gender: q["gender"] = gender
    if pedigree is not None: q["pedigree"] = pedigree
    if city: q["city"] = {"$regex": city, "$options": "i"}
    if owner_id: q["owner_id"] = owner_id

    pets = get_documents("pet", q, limit=100)
    for p in pets:
        p["id"] = str(p.pop("_id"))
    return pets

# ----- Swipes & Matches -----

@app.post("/swipe")
def swipe(like: Like):
    # record like/pass
    if like.liker_pet_id == like.target_pet_id:
        raise HTTPException(status_code=400, detail="Cannot swipe your own pet")
    create_document("like", like)

    # check for mutual like
    mutual = db["like"].find_one({
        "liker_pet_id": like.target_pet_id,
        "target_pet_id": like.liker_pet_id,
        "action": "like"
    })
    if like.action == 'like' and mutual:
        # create match if not exists
        liker_pet = db["pet"].find_one({"_id": oid(like.liker_pet_id)})
        target_pet = db["pet"].find_one({"_id": oid(like.target_pet_id)})
        if not liker_pet or not target_pet:
            return {"status": "recorded", "match": False}
        # prevent duplicate matches
        exists = db["match"].find_one({
            "$or": [
                {"pet_a_id": like.liker_pet_id, "pet_b_id": like.target_pet_id},
                {"pet_a_id": like.target_pet_id, "pet_b_id": like.liker_pet_id},
            ]
        })
        if not exists:
            match_id = create_document("match", Match(
                pet_a_id=like.liker_pet_id,
                pet_b_id=like.target_pet_id,
                owner_a_id=liker_pet["owner_id"],
                owner_b_id=target_pet["owner_id"],
            ))
            return {"status": "match", "match_id": match_id}
    return {"status": "recorded", "match": False}

@app.get("/matches/{owner_id}")
def list_matches(owner_id: str):
    matches = list(db["match"].find({"$or": [{"owner_a_id": owner_id}, {"owner_b_id": owner_id}]}))
    for m in matches:
        m["id"] = str(m.pop("_id"))
    return matches

# ----- Messaging -----

class SendMessage(BaseModel):
    match_id: str
    sender_pet_id: str
    sender_owner_id: str
    text: str

@app.post("/messages")
def send_message(payload: SendMessage):
    # verify match exists and sender belongs to match
    match = db["match"].find_one({"_id": oid(payload.match_id)})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if payload.sender_owner_id not in [match["owner_a_id"], match["owner_b_id"]]:
        raise HTTPException(status_code=403, detail="Not part of this match")
    msg_id = create_document("message", Message(**payload.model_dump()))
    return {"id": msg_id}

@app.get("/messages/{match_id}")
def get_messages(match_id: str):
    msgs = list(db["message"].find({"match_id": match_id}).sort("created_at", 1))
    for m in msgs:
        m["id"] = str(m.pop("_id"))
    return msgs

# ----- Announcements -----

@app.post("/announcements")
def create_announcement(ann: Announcement):
    ann_id = create_document("announcement", ann)
    return {"id": ann_id}

@app.get("/announcements")
def list_announcements(species: Optional[str] = Query(None, regex="^(dog|cat)$")):
    q = {}
    if species:
        q["species"] = species
    anns = get_documents("announcement", q, limit=100)
    for a in anns:
        a["id"] = str(a.pop("_id"))
    return anns

# ----- Verification -----

@app.post("/verification")
def request_verification(v: Verification):
    v_id = create_document("verification", v)
    return {"id": v_id}

@app.get("/nearby")
def nearby_pets(
    species: str = Query(..., regex="^(dog|cat)$"),
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    city: Optional[str] = None,
    radius_km: Optional[int] = 50,
):
    # Basic approximation by city or rough lat/lng box
    q = {"species": species}
    if city:
        q["city"] = {"$regex": city, "$options": "i"}
    pets = get_documents("pet", q, limit=200)
    for p in pets:
        p["id"] = str(p.pop("_id"))
    return pets

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
