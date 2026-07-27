from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from .agent_semantic_models import SemanticAgentReplanRequest
from .models import AgentGenerateRequest, StrictModel
from .vision_inputs import (
    MAX_AGENT_IMAGES,
    SUPPORTED_AGENT_IMAGE_MEDIA_TYPES,
    decoded_agent_image_size,
    validate_agent_image_collection,
)


class AgentImageInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    data_url: SecretStr
    detail: Literal["auto", "low", "high"] = "high"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("image name cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> AgentImageInput:
        if self.media_type not in SUPPORTED_AGENT_IMAGE_MEDIA_TYPES:
            raise ValueError(f"unsupported image media type: {self.media_type}")
        decoded_agent_image_size(self.media_type, self.data_url.get_secret_value())
        return self


class VisionAgentGenerateRequest(AgentGenerateRequest):
    images: list[AgentImageInput] = Field(default_factory=list, max_length=MAX_AGENT_IMAGES)

    @model_validator(mode="after")
    def validate_images(self) -> VisionAgentGenerateRequest:
        validate_agent_image_collection(self.images)
        return self


class VisionSemanticAgentReplanRequest(SemanticAgentReplanRequest):
    images: list[AgentImageInput] = Field(default_factory=list, max_length=MAX_AGENT_IMAGES)

    @model_validator(mode="after")
    def validate_images(self) -> VisionSemanticAgentReplanRequest:
        validate_agent_image_collection(self.images)
        return self
