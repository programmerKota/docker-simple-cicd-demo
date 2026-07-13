# ADR-0001: Assemble before inventing

Status: Accepted for the first executable assembly.

## Decision rule

A component is selected only when it reduces custom code without removing a safety boundary. The score considers maturity, local operation, failure recovery, integration cost, licensing, observability, and replaceability. A higher raw feature count does not compensate for operational fragility.

## Selected core

| Capability | Selected component | Why |
|---|---|---|
| Personal AI runtime | OpenJarvis | Existing local inference, agents, operators, skills, memory, MCP, channels, evaluations, and telemetry. |
| Physical home control | Home Assistant | Existing device ecosystem, local deterministic automations, voice pipeline, and manual controls. |
| AI-to-home boundary | JARVIS Home MCP Gateway | Narrow typed capabilities, approval ownership, policy input construction, audit, and state verification. This is product-specific and remains ours. |
| Policy decision point | Open Policy Agent | Mature CNCF project, deny-by-default policies, structured JSON input/output, HTTP/embedded integration, policy tests, and broad operational support. |
| Durable Python workflows | DBOS | MIT-licensed Python library, Postgres-backed durable workflows, queues, scheduled jobs, exactly-once event processing, and built-in workflow observability without operating a separate workflow cluster. |
| Event/control bus | NATS JetStream | Lightweight server, replayable streams, durable consumers, request/reply, key-value state, and good edge-to-core fit. MQTT remains at the device edge. |
| Household ontology | Brick Schema | Established RDF ontology for spaces, equipment, sensors, points, feeds, and relationships. |
| Semantic graph store | Oxigraph / pyoxigraph | Embedded RDF/SPARQL store with permissive licensing; directly matches Brick's data model and avoids running a large graph database. |
| Room voice | Home Assistant Voice + Wyoming | Local wake word/STT/TTS pipeline and hardware satellites remain useful even if the general AI runtime is unavailable. |
| Browser/phone realtime media | LiveKit (optional profile) | Self-hostable WebRTC, interruption handling, realtime media, and agent transport. Not required for the first home-control path. |
| Local vision | Frigate (optional profile) | Local NVR/object events and Home Assistant integration. Only structured events enter the general AI context. |
| Telemetry | OpenTelemetry + Grafana-compatible stack | Vendor-neutral traces/metrics/logs and replaceable storage/visualization. |
| Backup | restic | Encrypted, deduplicated, incremental, verifiable backups with many storage targets. |
| Secrets as code | SOPS + age | Reviewable encrypted configuration without committing plaintext secrets. |
| Private remote access | WireGuard; Headscale/Tailscale profile | No direct public exposure of JARVIS, Home Assistant, Ollama, MCP, OPA, NATS, or databases. |

## Alternatives not selected for the first assembly

### Cedar instead of OPA

Cedar has an attractive analyzable authorization model, but OPA currently offers a more mature standalone enforcement service, HTTP API, operational ecosystem, and direct policy testing workflow. Cedar remains a future formal-verification profile, not a second simultaneous policy engine.

### Temporal instead of DBOS

Temporal is the maturity leader for large distributed workflow fleets. For a single household it introduces a larger control plane and operational surface. DBOS fits the existing Python service and needs only Postgres. Temporal remains the migration target if multi-home scale, multi-region workers, or workflow throughput outgrows DBOS.

### Restate instead of DBOS

Restate has an excellent single-binary architecture and durable services, but its server uses Business Source License 1.1 rather than an OSI-approved open-source license. It remains technically viable for private deployment, but is not the default foundation for this open product.

### Eclipse Ditto instead of Brick + Oxigraph

Ditto is a capable digital-twin platform, but it is operationally excessive for the first single-home deployment. Brick + Oxigraph supplies the semantic model and SPARQL querying with far fewer moving parts.

### Direct Home Assistant MCP access

Rejected for state-changing production tools. It would expose a large generic capability surface and bypass JARVIS Home policy, approval, idempotency, durable workflow, state witness, and audit guarantees. Direct HA MCP may be enabled read-only in a development profile.

### Node-RED or n8n as the physical workflow authority

Both are useful integration tools, but neither becomes the safety authority. Existing flows may trigger JARVIS requests; physical execution still passes through policy and durable workflow controls. Home Assistant remains responsible for deterministic local safety automations.

### Kubernetes/k3s for the first home

Rejected initially. Docker Compose plus explicit health checks, restart policies, backups, and dependency pinning has a smaller failure surface. Kubernetes remains a multi-node/high-availability deployment profile.

## Non-negotiable boundaries

1. The LLM never receives the Home Assistant token, OPA management credentials, database credentials, or backup keys.
2. OpenJarvis never receives a generic shell or generic Home Assistant service tool in the production profile.
3. A write is successful only after the reported physical state satisfies a postcondition.
4. Every action has an idempotency key, policy decision, actor, reason, exact arguments, and immutable audit record.
5. Locks, alarms, doors, cameras, microphones, and location data start denied and require separate capability designs.
6. Home Assistant deterministic automations and physical controls continue when all AI components are offline.
7. Component updates are pinned, tested in staging, and reversible. No unattended production auto-update.

## First vertical slice

The first assembled path is deliberately narrow:

```text
OpenJarvis request
  -> authenticated MCP tool: home_propose_light_action
  -> JARVIS Home validates typed arguments
  -> OPA evaluates identity, target, time, occupancy, and risk
  -> owner approval when required
  -> DBOS durable workflow obtains an idempotency key
  -> Home Assistant light service call
  -> wait for and verify resulting entity state
  -> NATS event + append-only audit
  -> only then report success
```

No additional write capability is added until this path passes unit, property, integration, restart, duplicate-delivery, network-loss, and rollback tests.