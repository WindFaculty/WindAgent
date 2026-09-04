"""Desktop application package."""

from .config import DesktopConfig
from .desktop_app import DesktopSupervisor, run_desktop_app
from .recording_adapter import NativeRecordingAdapter

__all__ = ["DesktopConfig", "DesktopSupervisor", "NativeRecordingAdapter", "run_desktop_app"]
