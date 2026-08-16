"""Runtime process request schema."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.data.domains import ALLOWED_DOMAINS


class ProcessInput(BaseModel):
    """Validated input for one dynamic process workflow request."""

    model_config = ConfigDict(extra="forbid")

    process_code: Optional[str] = Field(
        default=None, pattern=r"^P[0-9]{3,}$", min_length=4, max_length=32
    )
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1)
    description: str = Field(min_length=1)
    business_purpose: Optional[str] = None
    key_activities: Optional[str] = None
    current_challenges: Optional[str] = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        if value not in ALLOWED_DOMAINS:
            raise ValueError("domain must be one of the approved CuraPharm domains")
        return value
