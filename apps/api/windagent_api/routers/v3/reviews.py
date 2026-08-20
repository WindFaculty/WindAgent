"""
V3 Reviews Router — Generic Review System for Story Production Domain.
Covers storyboard, character revision, asset revision, production preview.
Decision is always pinned to revision_id + expected_version.

Phase 4: reviews, comments, and decisions are persisted through the
namespaced durable V3 resource authority. No module-level RAM stores.
"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import (
    NS_REVIEWS,
    NS_REVIEW_COMMENTS,
    NS_REVIEW_DECISIONS,
)

router = APIRouter(prefix="/api/v3/reviews", tags=["Reviews V3"])

VALID_SUBJECTS = {"storyboard", "character_revision", "asset_revision", "production_preview", "screenplay"}


class ReviewCommentResource(BaseModel):
    id: str
    review_id: str
    author: str
    role: str = "Reviewer"
    text: str = ""
    timestamp: str = ""


class ReviewDecisionResource(BaseModel):
    id: str
    review_id: str
    decision: str
    revision_id: str
    expected_version: int
    reason: str = ""
    decided_by: str = ""
    decided_at: str = ""


class ReviewResource(BaseModel):
    id: str
    subject_type: str
    subject_id: str
    episode_id: Optional[str] = None
    project_id: Optional[str] = None
    status: str = "PENDING"
    comments_count: int = 0
    decision: Optional[ReviewDecisionResource] = None
    created_at: str = ""
    updated_at: str = ""


class CreateReviewRequest(BaseModel):
    subject_type: str = Field(..., description="storyboard | character_revision | asset_revision | production_preview | screenplay")
    subject_id: str = Field(..., min_length=1)
    episode_id: Optional[str] = None
    project_id: Optional[str] = None


class CreateReviewCommentRequest(BaseModel):
    author: str = Field(..., min_length=1, max_length=200)
    role: str = "Reviewer"
    text: str = Field(..., min_length=1, max_length=5000)


class SubmitReviewDecisionRequest(BaseModel):
    decision: str = Field(..., description="APPROVED | REVISION_NEEDED | REJECTED")
    revision_id: str = Field(..., min_length=1)
    expected_version: int = Field(..., description="Pinned revision version — optimistic lock")
    reason: str = Field("", max_length=2000)
    decided_by: str = Field(..., min_length=1)


async def _review_to_resource(r: Dict[str, Any], service: V3ResourceService) -> ReviewResource:
    comments = await service.list(NS_REVIEW_COMMENTS)
    comments = [c for c in comments if c.get("review_id") == r["id"]]
    decisions = await service.list(NS_REVIEW_DECISIONS)
    decision_data = next((d for d in decisions if d.get("review_id") == r["id"]), None)
    decision = ReviewDecisionResource(**decision_data) if decision_data else None
    return ReviewResource(
        id=r["id"],
        subject_type=r["subject_type"],
        subject_id=r["subject_id"],
        episode_id=r.get("episode_id"),
        project_id=r.get("project_id"),
        status=r.get("status", "PENDING"),
        comments_count=len(comments),
        decision=decision,
        created_at=r.get("created_at", ""),
        updated_at=r.get("updated_at", ""),
    )


@router.get("", response_model=List[ReviewResource], operation_id="reviews.list")
async def list_reviews(
    subject_type: Optional[str] = Query(None),
    episode_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[ReviewResource]:
    """List reviews filtered by subject type, episode, project, or status."""
    reviews = await service.list(NS_REVIEWS)
    if subject_type:
        reviews = [r for r in reviews if r["subject_type"] == subject_type]
    if episode_id:
        reviews = [r for r in reviews if r.get("episode_id") == episode_id]
    if project_id:
        reviews = [r for r in reviews if r.get("project_id") == project_id]
    if status_filter:
        reviews = [r for r in reviews if r.get("status") == status_filter]
    return [await _review_to_resource(r, service) for r in reviews]


@router.post("", response_model=ReviewResource, status_code=status.HTTP_201_CREATED, operation_id="reviews.create")
async def create_review(
    body: CreateReviewRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ReviewResource:
    """Create a new review session for a subject."""
    if body.subject_type not in VALID_SUBJECTS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"subject_type must be one of: {', '.join(sorted(VALID_SUBJECTS))}")
    review_id = f"review-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    new_review: Dict[str, Any] = {
        "id": review_id,
        "subject_type": body.subject_type,
        "subject_id": body.subject_id,
        "episode_id": body.episode_id,
        "project_id": body.project_id,
        "status": "PENDING",
        "created_at": now,
        "updated_at": now,
    }
    created = await service.create(NS_REVIEWS, review_id, new_review)
    return await _review_to_resource(created, service)


@router.get("/{review_id}", response_model=ReviewResource, operation_id="reviews.get")
async def get_review(
    review_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ReviewResource:
    """Get a review with its comments and decision."""
    review = await service.get(NS_REVIEWS, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Review '{review_id}' not found.")
    return await _review_to_resource(review, service)


@router.post("/{review_id}/comments", response_model=ReviewCommentResource, status_code=status.HTTP_201_CREATED, operation_id="reviews.addComment")
async def add_review_comment(
    review_id: str = Path(...),
    body: CreateReviewCommentRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ReviewCommentResource:
    """Add a comment to a review thread."""
    review = await service.get(NS_REVIEWS, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Review '{review_id}' not found.")

    comment_id = f"cmt-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    comment: Dict[str, Any] = {
        "id": comment_id,
        "review_id": review_id,
        "author": body.author,
        "role": body.role,
        "text": body.text,
        "timestamp": now,
    }
    created = await service.create(NS_REVIEW_COMMENTS, comment_id, comment)

    updates = dict(review)
    updates["updated_at"] = now
    await service.update(NS_REVIEWS, review_id, updates, review["version"])
    return ReviewCommentResource(**created)


@router.get("/{review_id}/comments", response_model=List[ReviewCommentResource], operation_id="reviews.listComments")
async def list_review_comments(
    review_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[ReviewCommentResource]:
    """Retrieve all comments for a review thread."""
    review = await service.get(NS_REVIEWS, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Review '{review_id}' not found.")
    comments = await service.list(NS_REVIEW_COMMENTS)
    comments = [c for c in comments if c.get("review_id") == review_id]
    return [ReviewCommentResource(**c) for c in comments]


@router.post("/{review_id}/decision", response_model=ReviewDecisionResource, operation_id="reviews.submitDecision")
async def submit_review_decision(
    review_id: str = Path(...),
    body: SubmitReviewDecisionRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ReviewDecisionResource:
    """
    Submit a review decision pinned to a specific revision_id + expected_version.
    Prevents approving a mutable (un-versioned) object.
    """
    review = await service.get(NS_REVIEWS, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Review '{review_id}' not found.")

    if body.decision not in ("APPROVED", "REVISION_NEEDED", "REJECTED"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="decision must be APPROVED | REVISION_NEEDED | REJECTED")

    decisions = await service.list(NS_REVIEW_DECISIONS)
    existing = next((d for d in decisions if d.get("review_id") == review_id), None)
    if existing and existing.get("decision") in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Review '{review_id}' already has a terminal decision: {existing['decision']}.")

    dec_id = f"dec-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    decision: Dict[str, Any] = {
        "id": dec_id,
        "review_id": review_id,
        "decision": body.decision,
        "revision_id": body.revision_id,
        "expected_version": body.expected_version,
        "reason": body.reason,
        "decided_by": body.decided_by,
        "decided_at": now,
    }
    created = await service.create(NS_REVIEW_DECISIONS, dec_id, decision)

    updates = dict(review)
    updates["status"] = "APPROVED" if body.decision == "APPROVED" else ("REJECTED" if body.decision == "REJECTED" else "REVISION_NEEDED")
    updates["updated_at"] = now
    await service.update(NS_REVIEWS, review_id, updates, review["version"])

    return ReviewDecisionResource(**created)
