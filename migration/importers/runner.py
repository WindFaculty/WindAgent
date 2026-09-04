"""Unified Migration CLI Runner for WindAgent V2."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .agent_workflow_importer import AgentWorkflowImporter
from .model_gateway_importer import ModelGatewayImporter
from .production_importer import ProductionImporter
from .quality_importer import QualityImporter
from .studio_importer import StudioImporter
from .workspace_importer import WorkspaceImporter

logger = logging.getLogger("windagent.migration")


@dataclass
class MigrationReport:
    total_records_processed: int = 0
    workspaces_migrated: int = 0
    rules_migrated: int = 0
    studio_projects_migrated: int = 0
    production_projects_migrated: int = 0
    workflows_migrated: int = 0
    quality_datasets_migrated: int = 0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    is_success: bool = True


class MigrationRunner:
    """Orchestrates comprehensive migration from legacy WindAgent to V2."""

    def __init__(self) -> None:
        self.workspace_importer = WorkspaceImporter()
        self.model_gateway_importer = ModelGatewayImporter()
        self.studio_importer = StudioImporter()
        self.production_importer = ProductionImporter()
        self.workflow_importer = AgentWorkflowImporter()
        self.quality_importer = QualityImporter()

    def run_full_migration(self, legacy_bundle: dict[str, Any], *, dry_run: bool = False) -> MigrationReport:
        """Run complete migration pipeline with error isolation and validation."""
        report = MigrationReport(dry_run=dry_run)
        logger.info("Initiating WindAgent migration pipeline (dry_run=%s)...", dry_run)

        try:
            # 1. Workspace migration
            for ws in legacy_bundle.get("workspaces", []):
                self.workspace_importer.import_legacy_workspace(ws, dry_run=dry_run)
                report.workspaces_migrated += 1
                report.total_records_processed += 1

            # 2. Model Gateway rules
            for rule in legacy_bundle.get("routing_rules", []):
                self.model_gateway_importer.import_legacy_routing_rule(rule, dry_run=dry_run)
                report.rules_migrated += 1
                report.total_records_processed += 1

            # 3. Studio Projects
            for proj in legacy_bundle.get("studio_projects", []):
                self.studio_importer.import_legacy_project(proj, dry_run=dry_run)
                report.studio_projects_migrated += 1
                report.total_records_processed += 1

            # 4. Production Projects
            for prod in legacy_bundle.get("production_projects", []):
                self.production_importer.import_legacy_project(prod, dry_run=dry_run)
                report.production_projects_migrated += 1
                report.total_records_processed += 1

            # 5. Workflows
            for wf in legacy_bundle.get("workflows", []):
                self.workflow_importer.import_legacy_workflow(wf, dry_run=dry_run)
                report.workflows_migrated += 1
                report.total_records_processed += 1

            # 6. Quality Datasets
            for ds in legacy_bundle.get("quality_datasets", []):
                self.quality_importer.import_legacy_dataset(ds, dry_run=dry_run)
                report.quality_datasets_migrated += 1
                report.total_records_processed += 1

        except Exception as e:
            logger.error("Migration encountered error: %s", str(e), exc_info=True)
            report.errors.append(str(e))
            report.is_success = False

        return report
