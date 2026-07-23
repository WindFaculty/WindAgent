"""
Detection Package for WindAgent Provider Subsystem V3.
Exports EndpointDetector, ProbePlanRunner, and sanitize_url.
"""

from windagent_providers.detection.url_sanitizer import sanitize_url
from windagent_providers.detection.fingerprints import detect_vendor_from_url_or_key
from windagent_providers.detection.probe_plan import ProbePlanRunner
from windagent_providers.detection.detector import EndpointDetector

__all__ = [
    "sanitize_url",
    "detect_vendor_from_url_or_key",
    "ProbePlanRunner",
    "EndpointDetector",
]
