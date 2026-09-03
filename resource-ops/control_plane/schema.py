"""gateway_resources.json v1 的版本化 schema + 校验辅助。"""
import json
import re

SCHEMA = {
    "schema_version": 1,
    "required_top": ["schema_version", "generation_id", "generated_at", "source", "resources"],
    "resource_required": ["resource_id", "channel", "unified_model", "upstream_model",
                          "credential_ref", "status", "limits", "capabilities"],
}

SID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


def check_schema_version(version):
    return version == SCHEMA["schema_version"]
