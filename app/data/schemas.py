"""Validation models for curated process seed records."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.data.domains import ALLOWED_DOMAINS


class ProcessSeed(BaseModel):
    """One database-independent curated process record."""

    model_config = ConfigDict(extra="forbid")

    process_code: str = Field(pattern=r"^P[0-9]{3,}$", min_length=4, max_length=32)
    name: str = Field(min_length=5, max_length=255)
    domain: str
    description: str = Field(min_length=20)
    business_purpose: str = Field(min_length=15)
    key_activities: str = Field(min_length=20)
    current_challenges: str = Field(min_length=20)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        if value not in ALLOWED_DOMAINS:
            raise ValueError("domain must be one of the approved CuraPharm domains")
        return value

