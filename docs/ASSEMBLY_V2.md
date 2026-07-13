# JARVIS Home — Assembly Architecture v2

Status: architecture baseline for the `assembly-v2` branch. The existing `main` branch remains untouched.

## Product boundary

JARVIS Home is not another general agent framework and not another device hub. It is the safety-critical household intelligence layer between a personal AI runtime and the physical home.

```text
Voice / phone / browser / messages
                 |
                 v
OpenJarvis — reasoning, models, agents, skills, memory, evaluation
                 |
                 | MCP (read-only discovery + policy-gated action tools)
                 v
JARVIS Home Gateway — identity, intent, policy, simulation, approval,
                      durable execution, state verification, audit
                 |
                 v
Home Assistant — devices, entities, deterministic automations, protocols
                 |
        Zigbee / Matter / Z-Wave / MQTT / LAN devices
```

The language model never receives a raw Home Assistant token and never calls the Home Assistant service API directly.

## Selected components

### Intelligence: OpenJarvis

Use OpenJarvis as the upstream personal-AI substrate rather than rebuilding agent loops, model routing, skills, memory backends, evaluation, telemetry, channels, or continuous operators.

Pinned upstream: `open-jarvis/OpenJarvis@6240c59ca3305c5656075cc54cd7ff32df8dca0e`

Integration rule: consume through its public server/MCP/configuration surfaces. Do not fork unless an upstream defect cannot be solved externally.

### Physical home: Home Assistant

Home Assistant remains the sole device abstraction and deterministic automation system. Safety and life-critical behavior must continue to work when OpenJarvis or the local LLM is unavailable.

JARVIS Home consumes entity state and invokes narrowly scoped services through a dedicated service account/token.

### Tool boundary: MCP

JARVIS Home becomes a domain-specific MCP server. It exposes a deliberately small tool catalog:

- `home.observe`
- `home.search_entities`
- `home.propose_action`
- `home.execute_plan`
- `home.explain_state`
- `home.list_pending_approvals`
- `home.approve`
- `home.cancel`

Raw generic service calls are not exposed to the model. Tool schemas are versioned and validated server-side.

### Durable events: NATS JetStream

Use NATS subjects as the internal event contract and JetStream for replay, durable consumers, idempotency keys, and recovery.

Example subjects:

```text
home.observation.v1
home.intent.v1
home.plan.proposed.v1
home.plan.authorized.v1
home.action.requested.v1
home.action.completed.v1
home.action.failed.v1
home.alert.v1
```

MQTT remains an edge/device protocol where Home Assistant or Frigate already uses it. NATS is the internal control-plane bus; the two are not interchangeable.

### Durable workflows: Temporal

Use Temporal only for multi-step actions whose progress must survive process crashes, network loss, or machine restarts. OpenJarvis operators continue to handle cognitive monitoring and analysis; Temporal handles deterministic physical workflows.

Required workflow properties:

- stable workflow and action IDs;
- idempotent activities;
- timeouts and bounded retries;
- compensation/rollback steps;
- post-action state witnesses;
- human approval signals;
- cancellation and emergency stop.

### Authorization: Cedar-based pre-action gateway

Every action is evaluated outside the LLM process with deny-by-default policy. Policy inputs include:

- authenticated person/device;
- verified current user intent;
- action and exact arguments;
- target entity, room, and household zone;
- current and predicted state;
- time and occupancy;
- risk class and cumulative action budget;
- whether a fresh approval or state witness exists.

Authorization produces a signed decision receipt. The model cannot read or modify the policy store.

The existing JARVIS Home approval, audit, and risk-classification code is retained as migration material, then replaced incrementally behind compatibility tests.

### Household semantics: Brick Schema + thin twin service

Use Brick classes and relationships to describe floors, rooms, equipment, sensors, occupants, feeds, and controls. The twin service maps Home Assistant entity/device/area registries into this semantic graph.

The twin stores:

- reported state;
- desired state;
- predicted state;
- freshness and confidence;
- provenance;
- relationships and safety constraints.

Eclipse Ditto is not included in the first assembly because it adds substantial operational weight for one household. Re-evaluate it for multiple homes, remote device fleets, or independent twin APIs.

### Voice

Use two complementary paths:

1. Home Assistant Voice/Wyoming for room satellites, wake words, local home-control speech, physical microphone mute, Whisper/Speech-to-Phrase, and Piper.
2. Self-hosted LiveKit Agents for low-latency phone/browser sessions, interruptions, turn detection, multimodal streams, and remote WebRTC access.

The room satellite remains useful when the AI service is down; open-ended conversation may fall back to OpenJarvis.

### Vision and presence

Frigate is the optional local vision/NVR component. Only structured events and explicitly requested images cross into JARVIS Home. Continuous camera footage is never added to general conversational memory.

Room-level presence may be supplied by Home Assistant integrations such as BLE/mmWave systems. Presence is treated as uncertain sensor evidence, never as proof of identity.

### Observability

Instrument all services with OpenTelemetry. The optional operations profile uses Prometheus-compatible metrics, Loki-compatible logs, Tempo-compatible traces, and Grafana dashboards.

Mandatory product metrics include action success, state-witness failure, policy denial, approval latency, duplicate suppression, model/tool selection accuracy, response latency, energy use, and recovery time.

### Backup and supply chain

- restic for encrypted, deduplicated, verifiable backups;
- SOPS + age for declarative secrets/configuration;
- Trivy/Syft/Grype-class scanning in CI;
- signed images and SBOMs;
- Renovate/Dependabot updates only through CI and staged rollout;
- no unattended production auto-update of core home-control services.

## Components deliberately not selected

### OpenClaw runtime

Do not run a second general agent runtime beside OpenJarvis. It duplicates orchestration and broadens the attack surface. Import reviewed OpenClaw skills through OpenJarvis's skill compatibility instead.

### Direct ha-mcp write access

Useful for discovery and experimentation, but unrestricted Home Assistant tools would bypass household policy, simulation, approval, and workflow guarantees. Production writes must pass through JARVIS Home Gateway.

### OPA alongside Cedar

Running two policy languages creates drift. Cedar is the primary authorization language. Domain safety invariants remain typed application code with property-based tests.

### Eclipse Ditto in the first deployment

Strong digital-twin framework, but too operationally heavy for the initial single-home target. Brick plus a thin service gives the required semantics with less failure surface.

### Automatic container updates

Rejected. Every upstream update must pass compatibility, policy, simulation, and rollback tests before promotion.

## Degradation hierarchy

1. Home Assistant deterministic automations and physical controls.
2. JARVIS Home policy gateway and manually initiated safe actions.
3. OpenJarvis local-agent functions.
4. Open-ended LLM conversation and optional cloud collaboration.

Failure of a higher layer must not disable a lower layer.

## First assembly milestone

The first executable milestone is complete only when:

1. OpenJarvis discovers JARVIS Home through MCP.
2. Read-only Home Assistant state queries work.
3. A light-control request becomes a versioned plan.
4. Cedar denies unauthorized or ambiguous plans.
5. An approved plan starts a Temporal workflow.
6. The workflow issues an idempotent Home Assistant call.
7. The resulting entity state is verified.
8. NATS contains a replayable event trail.
9. The user receives success only after state verification.
10. Turning off OpenJarvis leaves Home Assistant automations operational.

No feature is promoted to `main` until this vertical path is tested end-to-end.