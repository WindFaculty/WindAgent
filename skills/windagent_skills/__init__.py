"""
Skills system for reusable capabilities - loader, registry, execution, versioning
"""

from windagent_skills.loader.manager import SkillManager
from windagent_skills.manifest.manifest import SkillManifest

__version__ = "0.3.0"
__all__ = ["SkillManager", "SkillManifest"]
