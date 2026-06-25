"""Shared data contracts — every scraper and engine speaks this language."""

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class IdentifierType(str, Enum):
    """What the investigator provides as a seed."""

    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    USERNAME = "username"
    UPI = "upi"
    FACE = "face"


class SourceTool(str, Enum):
    """Enumeration of data source tool identifiers."""

    MAIGRET = "maigret"
    GITHUB = "github"
    HOLEHE = "holehe"
    PHONEINFOGA = "phoneinfoga"
    IGNORANT = "ignorant"
    UPI_PARSER = "upi_parser"


class Platform(str, Enum):
    """Enumeration of platform identifiers."""

    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    AMAZON = "amazon"
    INSTAGRAM = "instagram"
    SNAPCHAT = "snapchat"
    OTHER = "other"



@dataclass
class Identifier:
    """A single investigation seed."""

    type: IdentifierType
    value: str


@dataclass
class RawProfile:
    """Single profile found by a data source."""

    type: str           # "social_account" | "email" | "phone" | "username" | "upi" | "breach" | "post" | "name"
    value: str          # the actual identifier or content
    platform: str       # "instagram" | "github" | "telegram" | "hibp" | etc.
    source_url: str     # where it was found
    data_mode: str      # "live" | "mock"
    metadata: dict = field(default_factory=dict)   # platform-specific extras
    collected_at: str = ""      # ISO timestamp
    sha256: str = ""            # hash of value+platform+source_url


@dataclass
class SignalResult:
    """Output of a single signal comparison between two profiles."""

    signal_name: str
    weight: int
    matched: bool
    detail: str


@dataclass
class LinkedIdentity:
    """A cluster of profiles believed to belong to the same person."""

    cluster_id: str
    profiles: list[RawProfile]
    signals: list[SignalResult] = field(default_factory=list)
    confidence_score: float = 0.0
    tier: str = "REJECT"
    is_red_herring: bool = False
    red_herring_reason: str = ""
    why_explanation: list[str] = field(default_factory=list)


def compute_hash(*parts: str) -> str:
    """SHA-256 of colon-joined parts — used for evidence integrity."""
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()
