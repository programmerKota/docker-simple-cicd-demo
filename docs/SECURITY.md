# Security and threat model

## Assets

- Home Assistant long-lived token.
- Household occupancy and device state.
- Private conversation and memory data.
- Files exposed through configured workspace roots.
- Authority to operate lights, climate, locks, alarms, covers, media devices, and scripts.
- The local encryption master key.

## Trust boundaries

1. Browser to JARVIS HTTP API.
2. JARVIS to Ollama.
3. JARVIS to Home Assistant.
4. JARVIS to the host filesystem and subprocess layer.
5. Core process to optional local plugins.

The LLM is treated as an untrusted planner. Tool output and remembered content are also treated as untrusted data, not instructions.

## Implemented controls

### Authentication

- Passwords are stored using Argon2id through `argon2-cffi`.
- Sessions are signed, time-limited, bearer tokens.
- Login failures are rate-limited per source address.
- Browser tokens are stored in `sessionStorage`, not cookies or persistent local storage.

### Authorization and approvals

- Every tool has a declared risk.
- The policy engine may escalate risk based on arguments.
- Medium and high risks require an expiring one-time approval.
- Critical core actions are denied.
- Approval is bound to the exact stored payload and claimed transactionally.
- A rejected or expired approval cannot be replayed.

### Secret handling

- Integration secrets are encrypted with Fernet before database storage.
- The master key is generated separately and never included in backups.
- Known secret field names are redacted from audit details.
- The API never returns the Home Assistant token.

### Files and commands

- Paths are canonicalized and must remain below configured roots.
- Symlink and `..` escapes are rejected by resolved-path containment checks.
- Binary and oversized reads are refused.
- Writes use a temporary file and atomic replacement.
- Shell is disabled by default.
- Commands use argument arrays with `shell=False`.
- Only allowlisted executable basenames are accepted.
- Working directories remain inside configured roots.
- Environment variables are reduced and execution time is bounded.

### Network and web

- Trusted Host and restrictive CORS middleware are enabled.
- CSP, frame denial, MIME sniffing denial, referrer restriction, and permissions policy headers are set.
- Request bodies are size-limited.
- Docker runs as a non-root user with a read-only root filesystem, no capabilities, and `no-new-privileges`.
- The default deployment is LAN-only and documentation forbids direct port forwarding.

### Audit

Each audit row hashes canonical content and the prior hash. This is tamper-evident, not tamper-proof: an attacker with full database and application access could rewrite the entire chain. For stronger assurance, periodically export the latest hash to an external append-only destination.

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| Prompt injection asks the model to unlock a door | Argument-aware policy escalates lock operations and requires exact approval |
| Tool output tells the agent to ignore policy | The policy is code outside the model context |
| Stolen database reveals HA token | Token is encrypted; master key is separate |
| Malicious path reads arbitrary files | Canonical root containment and no unconfigured roots |
| Model invents command success | System prompt plus structured tool results; failures are returned and audited |
| Remote brute force | Rate limit, strong generated password, private network recommendation |
| Compromised plugin | Plugins are disabled and allowlisted; plugins remain fully trusted local code |
| Compromised host administrator | Out of scope; host admin can read process memory and replace code |
| Physical attacker steals both DB and master key | Full secret compromise; use full-disk encryption and secured backups |

## Deployment requirements

- Enable BitLocker, FileVault, or LUKS.
- Keep Home Assistant and JARVIS patched.
- Do not reuse the JARVIS password.
- Keep `master.key` out of synced folders and source control.
- Back up `master.key` separately in an encrypted password manager or offline medium.
- Use a VPN rather than public port forwarding.
- Review Home Assistant entity permissions and expose only necessary devices.
- Keep locks and alarm disarming in the high-risk approval category.

## Reporting vulnerabilities

Do not open a public issue containing tokens, database copies, recordings, addresses, entity IDs that reveal occupancy, or exploit details for an unpatched deployment. Revoke exposed Home Assistant tokens immediately.
