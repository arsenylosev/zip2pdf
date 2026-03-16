"""
Pydantic request / response schemas for the FastAPI routes.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import ALLOWED_IMAGE_DOMAINS, settings


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-z0-9-]+$")
    password: str = Field(..., min_length=6, max_length=128)


class UserPublic(BaseModel):
    id: int
    username: str
    role: str = "user"
    is_active: bool


class CreateUserRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9-]+$",
        description="Только строчные буквы, цифры и дефис (a-z, 0-9, -)",
    )
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="user", pattern=r"^(admin|user)$")


class SetRoleRequest(BaseModel):
    role: str = Field(..., pattern=r"^(admin|user)$")


class BalanceUpdateRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to add")


class BalanceTransferRequest(BaseModel):
    source: str = Field(..., pattern=r"^(main|llm)$")
    target: str = Field(..., pattern=r"^(main|llm)$")
    amount: float | None = Field(default=None, gt=0)
    transfer_all: bool = Field(default=False, description="Transfer entire source balance (ignores amount)")

    @model_validator(mode="after")
    def validate_transfer(self) -> "BalanceTransferRequest":
        if self.source == self.target:
            raise ValueError("source and target must be different")
        if not self.transfer_all and self.amount is None:
            raise ValueError("amount is required when transfer_all is false")
        return self


# ---------------------------------------------------------------------------
# VM Creation
# ---------------------------------------------------------------------------

class CreateVMRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=253)
    cpu: int = Field(..., ge=1)
    memory: float = Field(..., ge=1)
    storage: float = Field(..., ge=10)
    image: str
    gpu: int = Field(default=0, ge=0)
    gpu_model: str | None = None

    hostname: str | None = None
    username: str | None = None
    ssh_key: str | None = None
    password: str | None = None
    ssh_pwauth: bool = False
    package_update: bool = False
    nvidia_driver_version: str | None = None
    additional_packages: str | None = None
    custom_cloudinit: str | None = None

    @field_validator("name")
    @classmethod
    def validate_dns_name(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", v):
            raise ValueError(
                "Must be lowercase alphanumeric / '-', start and end with alphanumeric"
            )
        return v

    @field_validator("cpu")
    @classmethod
    def cap_cpu(cls, v: int) -> int:
        if v > settings.MAX_CPU_CORES:
            raise ValueError(f"CPU must be <= {settings.MAX_CPU_CORES}")
        return v

    @field_validator("memory")
    @classmethod
    def cap_memory(cls, v: float) -> float:
        if v > settings.MAX_MEMORY_GB:
            raise ValueError(f"Memory must be <= {settings.MAX_MEMORY_GB} GB")
        return v

    @field_validator("storage")
    @classmethod
    def cap_storage(cls, v: float) -> float:
        if v > settings.MAX_STORAGE_GB:
            raise ValueError(f"Storage must be <= {settings.MAX_STORAGE_GB} GB")
        return v

    @field_validator("gpu")
    @classmethod
    def cap_gpu(cls, v: int) -> int:
        if v > settings.MAX_GPU_COUNT:
            raise ValueError(f"GPU count must be <= {settings.MAX_GPU_COUNT}")
        return v

    @model_validator(mode="after")
    def gpu_model_required(self) -> "CreateVMRequest":
        if self.gpu > 0 and not self.gpu_model:
            raise ValueError("gpu_model is required when gpu > 0")
        return self

    @field_validator("image")
    @classmethod
    def validate_image(cls, v: str) -> str:
        if v in ("windows-installer", "windows-golden-image"):
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("Image URL must use http:// or https://")
        parsed = urlparse(v)
        if ALLOWED_IMAGE_DOMAINS and parsed.netloc not in ALLOWED_IMAGE_DOMAINS:
            raise ValueError(
                f"Domain not allowed: {parsed.netloc}. "
                f"Allowed: {', '.join(ALLOWED_IMAGE_DOMAINS)}"
            )
        return v


# ---------------------------------------------------------------------------
# VM Lifecycle (responses)
# ---------------------------------------------------------------------------

class VMActionResponse(BaseModel):
    success: bool
    message: str


class VMNameAvailability(BaseModel):
    available: bool
    exists: bool


# ---------------------------------------------------------------------------
# VM Details (responses)
# ---------------------------------------------------------------------------

class SSHServiceInfo(BaseModel):
    exists: bool
    node_port: int | None = None
    public_ip: str | None = None
    command: str | None = None


class VMInfoResponse(BaseModel):
    success: bool = True
    status: str
    cpu: str
    memory: str
    storage: str
    running: bool
    cloudinit_status: str | None = None
    cloudinit_message: str = ""
    datavolume_status: str | None = None
    allocated_ip: str | None = None
    ssh_service: SSHServiceInfo
    gpu_count: int | None = None
    gpu_model: str | None = None


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class CreateServiceRequest(BaseModel):
    port: int = Field(..., ge=1, le=65535)
    type: str = "custom"


class ServicePortInfo(BaseModel):
    name: str
    port: int
    nodePort: int
    protocol: str = "TCP"
    ssh_command: str | None = None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class DataVolumeInfo(BaseModel):
    name: str
    phase: str
    progress: str
    size: str
    pvc_name: str
    vm_name: str | None = None


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

class LLMChatRequest(BaseModel):
    messages: list[dict[str, str]] = Field(..., min_length=1)
    model: str | None = None  # Model ID from available-models (e.g. google/gemma-3-27b-it)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)


