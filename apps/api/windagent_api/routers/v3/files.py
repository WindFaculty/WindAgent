"""
V3 Files Router — Canonical Workspace File Abstraction Authority (Phase 13B).

FileResource is a workspace-scoped file abstraction, deliberately separate from
Assets. Every path is resolved through PathSandbox against WORKSPACE_ROOT —
arbitrary Windows paths from the frontend are rejected (sandbox enforced
server-side, no client-side reads of the host filesystem).
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from windagent_tools.filesystem.sandbox import PathSandbox
from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError

router = APIRouter(prefix="/api/v3/files", tags=["Files V3"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class FileResource(BaseModel):
    id: str
    path: str  # workspace-relative path
    name: str
    media_type: str
    size: int
    checksum: str
    created_at: str
    modified_at: str
    permissions: Dict[str, Any] = Field(default_factory=dict)


class CreateFileRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=1_000)
    name: str = Field(..., min_length=1, max_length=255)
    media_type: str = "application/octet-stream"
    content: str = Field(default="", max_length=50_000_000)


def _workspace_root(request: Request) -> Path:
    root = getattr(request.app.state, "workspace_root", None)
    if root is None:
        configured = os.getenv("WINDAGENT_WORKSPACE_ROOT")
        root = Path(configured) if configured else (Path.cwd() / "workspace")
        root.mkdir(parents=True, exist_ok=True)
        request.app.state.workspace_root = root
    return Path(root)


def _sandbox(request: Request) -> PathSandbox:
    return PathSandbox(_workspace_root(request))


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".json": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".csv": "text/csv",
        ".py": "text/x-python",
        ".ts": "text/typescript",
        ".tsx": "text/typescript",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".pdf": "application/pdf",
        ".html": "text/html",
    }
    return mapping.get(suffix, "application/octet-stream")


def _resource(request: Request, path: Path, checksum: Optional[str] = None) -> FileResource:
    stat = path.stat()
    rel = path.relative_to(_workspace_root(request))
    return FileResource(
        id=hashlib.sha256(str(rel).encode("utf-8")).hexdigest()[:16],
        path=rel.as_posix(),
        name=path.name,
        media_type=_mime_type(path),
        size=stat.st_size,
        checksum=checksum or "",
        created_at="",
        modified_at=str(stat.st_mtime),
        permissions={"read": path.is_file(), "write": os.access(path, os.W_OK)},
    )


@router.get("", response_model=List[FileResource], operation_id="files.list")
async def list_files(request: Request) -> List[FileResource]:
    """List workspace files. Returns real filesystem records only."""
    sandbox = _sandbox(request)
    resources: List[FileResource] = []
    for path in sorted(sandbox.workspace_root.rglob("*")):
        if path.is_dir():
            continue
        if any(part.startswith(".") for part in path.relative_to(sandbox.workspace_root).parts):
            continue
        resources.append(_resource(request, path))
    return resources


@router.post("", response_model=FileResource, operation_id="files.create")
async def create_file(body: CreateFileRequest, request: Request) -> FileResource:
    """Create a workspace file. Server-side sandbox enforcement — absolute or
    traversal paths outside WORKSPACE_ROOT are rejected."""
    sandbox = _sandbox(request)
    if os.path.isabs(body.path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Absolute host paths are not allowed; use a workspace-relative path.",
        )
    try:
        safe_path = sandbox.resolve_safe_path(body.path)
    except (ValueError, OSError, PermissionDeniedError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path rejected by workspace sandbox: {exc}",
        ) from exc
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(body.content, encoding="utf-8")
    return _resource(request, safe_path, checksum=hashlib.sha256(body.content.encode("utf-8")).hexdigest())


@router.post("/upload", response_model=FileResource, operation_id="files.upload")
async def upload_file(
    request: Request,
    file: UploadFile,
    path: str = "",
) -> FileResource:
    """Binary upload endpoint. filename is used only as a name hint; the target
    path is still sandbox-resolved server-side."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds 50MB limit")
    rel = path.strip().strip("/") or file.filename or "upload.bin"
    sandbox = _sandbox(request)
    if os.path.isabs(rel):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Absolute paths are not allowed")
    try:
        safe_path = sandbox.resolve_safe_path(rel)
    except (ValueError, OSError, PermissionDeniedError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path rejected by workspace sandbox: {exc}",
        ) from exc
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_bytes(content)
    return _resource(request, safe_path, checksum=hashlib.sha256(content).hexdigest())


@router.get("/{file_id}", response_model=FileResource, operation_id="files.get")
async def get_file(file_id: str, request: Request) -> FileResource:
    """Resolve a FileResource by its id (sha256 of workspace-relative path)."""
    sandbox = _sandbox(request)
    for path in sandbox.workspace_root.rglob("*"):
        if path.is_file() and _resource(request, path).id == file_id:
            return _resource(request, path)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in workspace")


@router.get("/{file_id}/download")
async def download_file(file_id: str, request: Request) -> FileResponse:
    """Download the file content. Only files inside the workspace sandbox can be served."""
    sandbox = _sandbox(request)
    for path in sandbox.workspace_root.rglob("*"):
        if path.is_file() and _resource(request, path).id == file_id:
            return FileResponse(path, media_type=_mime_type(path), filename=path.name)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in workspace")


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="files.delete")
async def delete_file(file_id: str, request: Request) -> None:
    sandbox = _sandbox(request)
    for path in sandbox.workspace_root.rglob("*"):
        if path.is_file() and _resource(request, path).id == file_id:
            path.unlink()
            return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in workspace")