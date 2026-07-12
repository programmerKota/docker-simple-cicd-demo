# Hardware deployment

## Recommended topology

```text
Internet
   │
Router ── private LAN / VPN only
   ├─ JARVIS host: Ollama + JARVIS Home
   ├─ Home Assistant host/appliance
   ├─ Zigbee / Z-Wave / Matter coordinators
   ├─ room voice satellites
   └─ phones, PCs, sensors, cameras and smart appliances
```

JARVIS does not replace Home Assistant's device ecosystem. Home Assistant remains the device abstraction and automation bus; JARVIS supplies natural language, memory, planning, policy, approvals, PC integration, and unified oversight.

## Compute tiers

### Existing PC

Best first deployment. Run Ollama natively for GPU access and JARVIS in Docker or Python. The user already controls model size and can replace the model without changing JARVIS.

### Dedicated mini PC

Suitable for always-on orchestration, Home Assistant, and small CPU models. Keep larger Ollama inference on a separate GPU workstation and point JARVIS at its private-LAN URL.

### GPU workstation

Best conversational quality and latency. Restrict Ollama to the private network. Avoid exposing its unauthenticated API outside trusted hosts.

## Voice satellites

A room satellite needs a microphone, speaker, wake-word process, and a secure connection to JARVIS. Practical options include:

- Home Assistant Voice hardware and Assist satellites;
- ESPHome voice satellites;
- Raspberry Pi or mini-PC satellites using openWakeWord plus a local client;
- a phone browser using the built-in JARVIS recording button.

Wake word and continuous-room audio are intentionally outside the core process because microphones require room-specific consent, echo cancellation, device drivers, and hardware tuning. The core exposes local transcription and speech endpoints for those satellites.

## Device onboarding order

1. Lights and read-only sensors.
2. Climate and media devices.
3. Presence sensors and cameras with privacy rules.
4. Covers and garage doors.
5. Locks and alarms last, keeping manual approval mandatory.

Start with fewer exposed entities and stable names. Large unfiltered entity catalogs reduce local-model reliability and make natural-language targeting ambiguous.

## Reliability

- Put the JARVIS and Home Assistant hosts on UPS power if they control critical routines.
- Keep physical controls usable when the AI stack is offline.
- Do not make heating, locks, alarms, medical equipment, or fire safety dependent on an LLM response.
- Use Home Assistant's deterministic automations for life-safety behavior; JARVIS may observe and explain them but should not be their sole controller.
