"""
backend/cases/collections_routes.py — case-collection (folder/watchlist) endpoints.

    GET    /collections                    my collections + membership map
    POST   /collections                    create a collection
    DELETE /collections/{collection_id}    delete a collection (+ its memberships)
    PUT    /cases/{case_id}/collections    set which collections a case belongs to
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.auth_middleware import get_current_user
from backend.cases.collections_service import (create_collection, delete_collection,
                                               list_collections, memberships,
                                               set_case_collections)

router = APIRouter(tags=["collections"])


class NewCollection(BaseModel):
    name: str
    color: str = ""


class CaseCollections(BaseModel):
    collection_ids: list[str] = []


@router.get("/collections")
def get_collections(user_id: str = Depends(get_current_user)):
    """All of this user's collections, plus {case_id: [collection_id]} memberships."""
    return {"collections": list_collections(user_id),
            "memberships": memberships(user_id)}


@router.post("/collections")
def post_collection(body: NewCollection, user_id: str = Depends(get_current_user)):
    try:
        return create_collection(user_id, body.name, body.color)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/collections/{collection_id}")
def remove_collection(collection_id: str, user_id: str = Depends(get_current_user)):
    if not delete_collection(user_id, collection_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"deleted": True}


@router.put("/cases/{case_id}/collections")
def put_case_collections(case_id: str, body: CaseCollections,
                         user_id: str = Depends(get_current_user)):
    result = set_case_collections(user_id, case_id, body.collection_ids)
    if result is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"collection_ids": result}
