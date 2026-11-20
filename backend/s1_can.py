"""Compatibility alias for the local old S1 SDK safe CAN extension."""
import sys
from S1_SDK import safe_can
sys.modules[__name__] = safe_can
