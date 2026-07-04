"""Pydantic schemas and data structures for the Agentic Web Browser module."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.ingestion.base_module import RawProfile, make_profile


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WebToolTarget(BaseModel):
    """Curated OSINT web tool definition."""
    id: str
    name: str
    description: str
    target_url: str
    query_placeholder: str
    icon: str = "🌐"
    category: str = "OSINT Web"


class AgenticLookupRequest(BaseModel):
    """Request payload to initiate an agentic browser task."""
    case_id: str
    tool_id: str = Field(..., description="ID of curated tool or 'custom'")
    query: str = Field(..., description="Target identifier (handle, email, name)")
    custom_url: Optional[str] = None
    custom_instruction: Optional[str] = None


class AgenticStepLog(BaseModel):
    """Log entry representing a single reasoning or DOM interaction step by the web agent."""
    step_index: int
    timestamp: str = Field(default_factory=_now_iso)
    action: str
    details: str
    status: str = "success"  # "success", "info", "warning", "error"


class ExtractedWebProfile(BaseModel):
    """Structured data extracted by the web agent from the DOM."""
    platform: str = "web"
    username: str
    value: str
    profile_url: Optional[str] = None
    bio: Optional[str] = None
    followers: Optional[Any] = None
    following: Optional[Any] = None
    fullname: Optional[str] = None
    profile_photo: Optional[str] = None
    additional_metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_raw_profile(self, data_mode: str = "agentic_web") -> RawProfile:
        """Converts extracted Pydantic schema to VERTEX's agnostic RawProfile dataclass."""
        md = dict(self.additional_metadata)
        if self.username:
            md["username"] = self.username           # so exact-seed / username signals fire
        if self.bio:
            md["bio"] = self.bio
        if self.followers is not None:
            md["followers"] = self.followers
        if self.following is not None:
            md["following"] = self.following
        if self.fullname:
            md["name"] = self.fullname
            md["fullname"] = self.fullname
        if self.profile_photo:
            md["photo_url"] = self.profile_photo     # key the photo pipeline / UI expect
            md["profile_photo"] = self.profile_photo
        md["agentic_source"] = True

        return make_profile(
            type="social_account",
            value=self.value or self.username,
            platform=(self.platform or "web").lower(),
            source_url=self.profile_url or f"https://{(self.platform or 'web').lower()}.com/{self.username}",
            metadata=md,
            data_mode=data_mode,
        )


class ExtractedProfilesResult(BaseModel):
    """Structured output the browser agent is constrained to return. A site may yield zero,
    one, or many profiles. `blocked` lets the agent report it was denied access
    (CAPTCHA / login wall) so we surface an honest 'blocked' state instead of fabricating.
    NEVER invent profiles — an empty list is the correct answer when nothing real was found."""
    profiles: List[ExtractedWebProfile] = Field(default_factory=list)
    blocked: bool = False
    notes: Optional[str] = None


class AgenticTaskStatus(BaseModel):
    """Full status representation of an asynchronous web agent task."""
    task_id: str
    case_id: str
    tool_id: str
    query: str
    # queued | navigating | extracting | correlating | complete | blocked | error
    status: str = "queued"
    step_logs: List[AgenticStepLog] = Field(default_factory=list)
    extracted_profiles: List[ExtractedWebProfile] = Field(default_factory=list)
    entities_added: int = 0
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
