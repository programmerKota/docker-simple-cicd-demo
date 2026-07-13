package jarvis.home

import rego.v1

policy_version := "home-policy-v1"

allowed_light_services := {"turn_on", "turn_off"}

default decision := {
    "allow": false,
    "require_approval": true,
    "reason": "No household policy grants this capability",
    "policy_version": "home-policy-v1",
}

decision := {
    "allow": true,
    "require_approval": true,
    "reason": "A local OpenJarvis agent may propose an idempotent light action; owner approval remains mandatory",
    "policy_version": policy_version,
} if {
    input.schema_version == 1
    input.actor.role == "agent"
    input.actor.source == "openjarvis-mcp"
    input.action.capability == "home.light.write"
    input.action.domain == "light"
    input.action.service in allowed_light_services
    startswith(input.action.entity_id, "light.")
    not input.context.emergency
    valid_brightness
}

valid_brightness if {
    input.action.brightness_pct == null
}

valid_brightness if {
    input.action.service == "turn_on"
    input.action.brightness_pct >= 1
    input.action.brightness_pct <= 100
}
