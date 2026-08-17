"""
V3 Project Templates Router — Canonical starter cinematic templates registry.
"""

from __future__ import annotations
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v3/project-templates", tags=["Project Templates V3"])


class ProjectTemplate(BaseModel):
    id: str = Field(..., description="Unique template identifier")
    title: str = Field(..., description="Starter project title")
    description: str = Field(..., description="Overview and setting logline")
    genre: str = Field(..., description="Primary genre classification")
    initial_episode: str = Field(..., description="Episode 1 default title")
    episode_brief: str = Field(..., description="Episode 1 logline / prompt brief")
    accent_color: str = Field(..., description="Theme accent color hex")


CURATED_TEMPLATES: List[ProjectTemplate] = [
    ProjectTemplate(
        id="tmpl_cyberpunk",
        title="Cyberpunk Odyssey 2099",
        description="Vũ trụ siêu đô thị ngầm tương lai nơi các hacker và người máy cyborg tìm kiếm ký ức đã mất.",
        genre="Cyberpunk / Sci-Fi",
        initial_episode="Tập 01: Mã Nguồn Thức Tỉnh",
        episode_brief="Khởi đầu với một tin tặc phát hiện đoạn mã bất thường trong hệ thống AI trung tâm.",
        accent_color="#38bdf8",
    ),
    ProjectTemplate(
        id="tmpl_fantasy",
        title="Biên Niên Sử Vùng Đất Rồng",
        description="Cuộc phiêu lưu huyền ảo qua các vương quốc cổ đại nhằm khôi phục viên ngọc nguyên tố bóng đêm.",
        genre="High Fantasy / Adventure",
        initial_episode="Tập 01: Tiếng Gọi Rừng Thiêng",
        episode_brief="Người giám hộ trẻ phát hiện dấu vết sinh vật thần thoại thức giấc sau một ngàn năm.",
        accent_color="#34d399",
    ),
    ProjectTemplate(
        id="tmpl_noir",
        title="Thám Tử Đêm Sương Mù",
        description="Những vụ án bí ẩn tại thành phố cảng những năm 1940 với các âm mưu ngầm và bí mật đen tối.",
        genre="Drama / Mystery Noir",
        initial_episode="Tập 01: Vết Bóng Trên Cầu Cảng",
        episode_brief="Một cuộc gọi ẩn danh lúc nửa đêm dẫn thám tử tư đến hiện trường vụ mất tích bí ẩn.",
        accent_color="#fbbf24",
    ),
    ProjectTemplate(
        id="tmpl_animation",
        title="Học Viện Pháp Thuật Tinh Tú",
        description="Hành trình của nhóm học viên trẻ khám phá những bí thuật bị lãng quên trong vũ trụ pháp thuật.",
        genre="Animation / Epic Saga",
        initial_episode="Tập 01: Lễ Khai Giảng Bí Ẩn",
        episode_brief="Học viên mới vô tình giải phóng một linh hồn cổ đại bị phong ấn trong thư viện cấm.",
        accent_color="#818cf8",
    ),
]


@router.get("", response_model=List[ProjectTemplate], operation_id="projects.getTemplates")
async def list_project_templates() -> List[ProjectTemplate]:
    """Retrieve list of curated cinematic project starter templates."""
    return CURATED_TEMPLATES
