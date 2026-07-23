"""
API V2 Tools endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/tools", tags=["Tools V2"])


class ToolInfo(BaseModel):
    name: str
    category: str
    description: str
    requires_permission: bool


REGISTERED_TOOLS_CATALOG = [
    {"name": "read_file", "category": "filesystem", "description": "Read contents of a file", "requires_permission": False},
    {"name": "write_to_file", "category": "filesystem", "description": "Create or overwrite a file", "requires_permission": True},
    {"name": "replace_file_content", "category": "filesystem", "description": "Edit lines in existing file", "requires_permission": True},
    {"name": "run_command", "category": "shell", "description": "Execute shell command in sandbox", "requires_permission": True},
    {"name": "grep_search", "category": "code_search", "description": "Search code using ripgrep", "requires_permission": False},
    {"name": "view_file", "category": "filesystem", "description": "View file content lines", "requires_permission": False},
]


@router.get("", response_model=List[ToolInfo])
async def list_tools() -> List[ToolInfo]:
    return [ToolInfo(**t) for t in REGISTERED_TOOLS_CATALOG]
