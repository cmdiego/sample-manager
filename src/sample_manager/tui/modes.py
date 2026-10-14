"""App mode enum for the TUI."""

from enum import Enum


class AppMode(Enum):
    BROWSE = "browse"
    SEARCH = "search"
    WAVEFORM_NAV = "waveform_nav"
