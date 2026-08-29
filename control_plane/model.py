"""Canonical Resource Model：飞书表结构与网关 JSON 之间的中间层。

resource_id 必须稳定唯一；credential_ref 只出现引用，绝不出现真实 secret；
capabilities 使用三态 supported/unsupported/unknown，unknown 永远不满足能力要求。
"""
from dataclasses import dataclass, field
from typing import Optional

SCHEMA_VERSION = 1

STATUSES = ("active", "paused", "draining", "disabled")
CAPABILITY_STATES = ("supported", "unsupported", "unknown")
CAPABILITY_KEYS = ("tools", "vision", "json_schema")


@dataclass
class Limits:
    rpm: Optional[int] = None
    rpd: Optional[int] = None
    concurrency: Optional[int] = None


@dataclass
class Capabilities:
    tools: str = "unknown"
    vision: str = "unknown"
    json_schema: str = "unknown"


@dataclass
class Resource:
    resource_id: str
    channel: str
    unified_model: str
    upstream_model: str
    credential_ref: str
    status: str = "active"
    expiry_at: Optional[str] = None
    limits: Limits = field(default_factory=Limits)
    capabilities: Capabilities = field(default_factory=Capabilities)
    source_record_id: Optional[str] = None


@dataclass
class Generation:
    schema_version: int = SCHEMA_VERSION
    generation_id: str = ""
    generated_at: str = ""
    source: dict = field(default_factory=dict)
    resources: list = field(default_factory=list)
