package jarvis.home_test

import data.jarvis.home
import rego.v1

base_input := {
    "schema_version": 1,
    "actor": {"id": "admin", "role": "agent", "source": "openjarvis-mcp"},
    "action": {
        "capability": "home.light.write",
        "domain": "light",
        "service": "turn_off",
        "entity_id": "light.study",
        "brightness_pct": null,
    },
    "context": {
        "timestamp": "2026-07-13T12:00:00Z",
        "owner_present": null,
        "fresh_owner_approval": false,
        "emergency": false,
    },
}

test_safe_light_proposal_is_allowed_but_requires_approval if {
    result := home.decision with input as base_input
    result.allow
    result.require_approval
}

test_lock_is_denied if {
    unsafe := object.union(base_input, {
        "action": {
            "capability": "home.lock.write",
            "domain": "lock",
            "service": "unlock",
            "entity_id": "lock.front_door",
            "brightness_pct": null,
        },
    })
    result := home.decision with input as unsafe
    not result.allow
}

test_wrong_source_is_denied if {
    unsafe := object.union(base_input, {
        "actor": {"id": "admin", "role": "agent", "source": "unknown"},
    })
    result := home.decision with input as unsafe
    not result.allow
}

test_out_of_range_brightness_is_denied if {
    action := object.union(base_input.action, {"service": "turn_on", "brightness_pct": 101})
    unsafe := object.union(base_input, {"action": action})
    result := home.decision with input as unsafe
    not result.allow
}

test_emergency_context_is_denied if {
    context := object.union(base_input.context, {"emergency": true})
    unsafe := object.union(base_input, {"context": context})
    result := home.decision with input as unsafe
    not result.allow
}
