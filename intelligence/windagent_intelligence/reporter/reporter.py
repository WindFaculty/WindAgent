"""
Task Reporter for WindAgent Intelligence (Phase 22).
Generates structured, machine-readable reports first, with Markdown/HTML as a render layer.
The canonical format is JSON/dict; Markdown and HTML are derived representations.
"""

from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("windagent.intelligence.reporter")


class ReportFormat(str, Enum):
    MACHINE = "machine"    # JSON/dict (canonical)
    MARKDOWN = "markdown"  # Human-readable Markdown
    HTML = "html"          # HTML render


@dataclass
class ReportSection:
    """A named section within an intelligence report."""
    title: str
    content: Any
    content_type: str = "text"  # text, json, table, code
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "content_type": self.content_type,
            "metadata": self.metadata,
        }


@dataclass
class IntelligenceReport:
    """Canonical machine-readable report from intelligence components.
    Machine format (dict) is the canonical format.
    Markdown and HTML are derived render layers.
    """
    report_id: str
    title: str
    report_type: str  # classification, planning, review, summary, general
    sections: List[ReportSection]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    format: ReportFormat = ReportFormat.MACHINE

    def to_dict(self) -> Dict[str, Any]:
        """Canonical machine-readable output."""
        return {
            "report_id": self.report_id,
            "title": self.title,
            "report_type": self.report_type,
            "format": self.format.value,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    def to_markdown(self) -> str:
        """Renders the report as Markdown (derived format)."""
        lines = [f"# {self.title}", f"*Type: {self.report_type}*", f"*Generated: {self.created_at}*", ""]

        for section in self.sections:
            lines.append(f"## {section.title}")
            if section.content_type == "code" or section.content_type == "json":
                content_str = json.dumps(section.content, indent=2) if isinstance(section.content, (dict, list)) else str(section.content)
                lines.append(f"```\n{content_str}\n```")
            elif section.content_type == "table" and isinstance(section.content, list):
                for row in section.content:
                    if isinstance(row, dict):
                        lines.append(f"- {json.dumps(row)}")
                    else:
                        lines.append(f"- {row}")
            else:
                lines.append(str(section.content))
            lines.append("")

        return "\n".join(lines)

    def to_html(self) -> str:
        """Renders the report as HTML (derived format)."""
        sections_html = ""
        for section in self.sections:
            content_str = str(section.content)
            content_str = content_str.replace("\n", "<br>")
            sections_html += f"""
            <div class="report-section">
                <h2>{section.title}</h2>
                <div class="section-content">{content_str}</div>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{self.title}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: auto; padding: 20px; }}
h1 {{ color: #333; }}
.report-section {{ margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 8px; }}
.metadata {{ color: #666; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>{self.title}</h1>
<p class="metadata">Type: {self.report_type} | Generated: {self.created_at}</p>
{sections_html}
</body>
</html>"""


class TaskReporter:
    """Generates intelligence reports in machine-readable format first.
    Markdown and HTML are derived render layers, not the canonical format.
    """

    def __init__(self):
        pass

    def create_report(
        self,
        title: str,
        report_type: str,
        sections: List[ReportSection],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IntelligenceReport:
        """Creates a canonical machine-readable report."""
        report_id = f"report_{hashlib.sha256(title.encode()).hexdigest()[:12]}"
        return IntelligenceReport(
            report_id=report_id,
            title=title,
            report_type=report_type,
            sections=sections,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Specialized report builders
    # ------------------------------------------------------------------

    def classification_report(
        self,
        classification_result: Any,
        task_prompt: str,
    ) -> IntelligenceReport:
        """Builds a report from a classification result."""
        sections = [
            ReportSection(title="Task Prompt", content=task_prompt[:500], content_type="text"),
            ReportSection(title="Classification", content=classification_result.to_dict(), content_type="json"),
            ReportSection(
                title="Workflow Candidates",
                content=[c.to_dict() for c in classification_result.workflow_candidates],
                content_type="json",
            ),
            ReportSection(
                title="Risk Assessment",
                content={
                    "risk_level": classification_result.risk_level.value,
                    "reasons": classification_result.risk_reasons,
                },
                content_type="json",
            ),
        ]
        return self.create_report(
            title="Task Classification Report",
            report_type="classification",
            sections=sections,
            metadata={
                "primary_label": classification_result.primary_label,
                "confidence": classification_result.confidence,
                "method": classification_result.classification_method,
                "used_model_fallback": classification_result.used_model_fallback,
            },
        )

    def planning_report(
        self,
        plan_result: Any,
        task_prompt: str,
    ) -> IntelligenceReport:
        """Builds a report from a planning result."""
        wf_def = plan_result.workflow_definition
        sections = [
            ReportSection(title="Task Prompt", content=task_prompt[:500], content_type="text"),
            ReportSection(
                title="Workflow Plan",
                content=plan_result.to_dict(),
                content_type="json",
            ),
            ReportSection(
                title="Validation",
                content=plan_result.validation.to_dict(),
                content_type="json",
            ),
            ReportSection(
                title="Steps",
                content=[
                    {"id": nid, "name": n.name, "tool": n.tool_name, "params": n.params}
                    for nid, n in wf_def.nodes.items()
                ],
                content_type="json",
            ),
            ReportSection(
                title="DAG Edges",
                content=[{"from": e.from_node_id, "to": e.to_node_id, "condition": e.condition} for e in wf_def.edges],
                content_type="json",
            ),
        ]
        return self.create_report(
            title="Task Planning Report",
            report_type="planning",
            sections=sections,
            metadata={
                "workflow_name": wf_def.name,
                "step_count": len(wf_def.nodes),
                "estimated_cost": plan_result.estimated_total_cost,
                "estimated_duration": plan_result.estimated_duration_seconds,
            },
        )

    def review_report(
        self,
        review_result: Any,
        task_prompt: str,
    ) -> IntelligenceReport:
        """Builds a report from a review result."""
        sections = [
            ReportSection(title="Task Prompt", content=task_prompt[:500], content_type="text"),
            ReportSection(title="Review Result", content=review_result.to_dict(), content_type="json"),
            ReportSection(
                title="Checks",
                content=[c.to_dict() for c in review_result.checks],
                content_type="json",
            ),
        ]
        return self.create_report(
            title="Task Review Report",
            report_type="review",
            sections=sections,
            metadata={
                "verdict": review_result.verdict.value,
                "passed": review_result.passed,
                "issues_count": len(review_result.issues),
                "has_verification_evidence": review_result.has_verification_evidence,
            },
        )

    def summary_report(
        self,
        summarization_result: Any,
        task_prompt: str,
    ) -> IntelligenceReport:
        """Builds a report from a summarization result."""
        sections = [
            ReportSection(title="Task Prompt", content=task_prompt[:500], content_type="text"),
            ReportSection(title="Summary", content=summarization_result.to_dict(), content_type="json"),
            ReportSection(title="Sources", content=summarization_result.sources, content_type="json"),
        ]
        return self.create_report(
            title="Task Summary Report",
            report_type="summary",
            sections=sections,
            metadata={
                "strategy": summarization_result.strategy.value,
                "source_count": summarization_result.source_count,
                "token_count": summarization_result.token_count,
            },
        )
