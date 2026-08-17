"""
V3 Reviews Router — Generic Review System for Story Production Domain.
Covers storyboard, character revision, asset revision, production preview.
Decision is always pinned to revision_id + expected_version.
"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

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


_REVIEWS: Dict[str, Dict[str, Any]] = {
    "review-sb-001": {
        "id": "review-sb-001",
        "subject_type": "storyboard",
        "subject_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "status": "PENDING",
        "created_at": "2026-08-13T08:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
    "review-screen-001": {
        "id": "review-screen-001",
        "subject_type": "screenplay",
        "subject_id": "rev-cb-001-v3",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "status": "APPROVED",
        "created_at": "2026-08-12T10:00:00Z",
        "updated_at": "2026-08-13T07:00:00Z",
    },
}

_REVIEW_COMMENTS: Dict[str, List[Dict[str, Any]]] = {
    "review-sb-001": [
        {
            "id": "cmt-001",
            "review_id": "review-sb-001",
            "author": "Director Agent",
            "role": "Director Agent",
            "text": "Cảnh mở đầu cần ánh sáng neon mạnh hơn để nhấn mạnh bầu không khí cyberpunk neo-noir. Góc máy hiện tại quá thẳng đứng.",
            "timestamp": "2026-08-13T10:42:00Z",
        },
        {
            "id": "cmt-002",
            "review_id": "review-sb-001",
            "author": "Producer Agent",
            "role": "Producer Agent",
            "text": "Thời lượng Scene 3 (190s) quá dài cho một đoạn đối thoại. Cân nhắc chia làm 2 phân cảnh.",
            "timestamp": "2026-08-13T11:15:00Z",
        },
    ],
    "review-screen-001": [],
}

_REVIEW_DECISIONS: Dict[str, Dict[str, Any]] = {
    "review-screen-001": {
        "id": "dec-screen-001",
        "review_id": "review-screen-001",
        "decision": "APPROVED",
        "revision_id": "rev-cb-001-v3",
        "expected_version": 3,
        "reason": "Bản thảo đáp ứng yêu cầu kịch tính và độ dài của tập phim.",
        "decided_by": "Director Agent",
        "decided_at": "2026-08-13T07:00:00Z",
    }
}


def _review_to_resource(r: Dict[str, Any]) -> ReviewResource:
    comments = _REVIEW_COMMENTS.get(r["id"], [])
    decision_data = _REVIEW_DECISIONS.get(r["id"])
    decision = ReviewDecisionResource(**decision_data) if decision_data else None
    return ReviewResource(
        id=r["id"],
        subject_type=r["subject_type"],
        subject_id=r["subject_id"],
        episode_id=r.get("episode_id"),
        project_id=r.get("project_id"),
        status=r["status"],
        comments_count=len(comments),
        decision=decision,
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


@router.get("", response_model=List[ReviewResource], operation_id="reviews.list")
async def list_reviews(
    subject_type: Optional[str] = Query(None),
    episode_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
) -> List[ReviewResource]:
    """List reviews filtered by subject type, episode, project, or status."""
    reviews = list(_REVIEWS.values())
    if subject_type:
        reviews = [r for r in reviews if r["subject_type"] == subject_type]
    if episode_id:
        reviews = [r for r in reviews if r.get("episode_id") == episode_id]
    if project_id:
        reviews = [r for r in reviews if r.get("project_id") == project_id]
    if status_filter:
        reviews = [r for r in reviews if r["status"] == status_filter]
    return [_review_to_resource(r) for r in reviews]


@router.post("", response_model=ReviewResource, status_code=status.HTTP_201_CREATED, operation_id="reviews.create")
async def create_review(body: CreateReviewRequest = ...) -> ReviewResource:
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
    _REVIEWS[review_id] = new_review
    _REVIEW_COMMENTS[review_id] = []
    return _review_to_resource(new_review)


@router.get("/{review_id}", response_model=ReviewResource, operation_id="reviews.get")
async def get_review(review_id: str = Path(...)) -> ReviewResource:
    """Get a review with its comments and decision."""
    if review_id not in _REVIEWS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Review '{review_id}' not found.")
    return _review_to_resource(_REVIEWS[review_id])


@router.post("/{review_id}/comments", response_model=ReviewCommentResource, status_code=status.HTTP_201_CREATED, operation_id="reviews.addComment")
async def add_review_comment(review_id: str = Path(...), body: CreateReviewCommentRequest = ...) -> ReviewCommentResource:
    """Add a comment to a review thread."""
    if review_id not in _REVIEWS:
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
    _REVIEW_COMMENTS.setdefault(review_id, []).append(comment)
    _REVIEWS[review_id]["updated_at"] = now
    return ReviewCommentResource(**comment)


@router.get("/{review_id}/comments", response_model=List[ReviewCommentResource], operation_id="reviews.listComments")
async def list_review_comments(review_id: str = Path(...)) -> List[ReviewCommentResource]:
    """Retrieve all comments for a review thread."""
    if review_id not in _REVIEWS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Review '{review_id}' not found.")
    return [ReviewCommentResource(**c) for c in _REVIEW_COMMENTS.get(review_id, [])]


@router.post("/{review_id}/decision", response_model=ReviewDecisionResource, operation_id="reviews.submitDecision")
async def submit_review_decision(review_id: str = Path(...), body: SubmitReviewDecisionRequest = ...) -> ReviewDecisionResource:
    """
    Submit a review decision pinned to a specific revision_id + expected_version.
    Prevents approving a mutable (un-versioned) object.
    """
    if review_id not in _REVIEWS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Review '{review_id}' not found.")

    if body.decision not in ("APPROVED", "REVISION_NEEDED", "REJECTED"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="decision must be APPROVED | REVISION_NEEDED | REJECTED")

    if review_id in _REVIEW_DECISIONS:
        existing = _REVIEW_DECISIONS[review_id]
        if existing["decision"] in ("APPROVED", "REJECTED"):
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
    _REVIEW_DECISIONS[review_id] = decision

    rev = _REVIEWS[review_id]
    rev["status"] = "APPROVED" if body.decision == "APPROVED" else ("REJECTED" if body.decision == "REJECTED" else "REVISION_NEEDED")
    rev["updated_at"] = now

    return ReviewDecisionResource(**decision)
