"""
Skills system for reusable capabilities - loader, registry, execution, versioning
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_skills.loader.manager import SkillManager
from windagent_skills.manifest.manifest import SkillManifest

__version__ = PRODUCT_VERSION
__all__ = ["SkillManager", "SkillManifest"]
