# AgentRun Runtime manifests

The files in `templates/` follow the current `agentrun/v1` container-runtime
schema. They are templates because AgentRun CLI does not interpolate `${...}`
inside YAML and the manifests require secrets.

Each manifest maps one dedicated ACR image to one managed AgentRuntime. The
runtime is the AgentRun cloud resource; it is not the Docker image itself.

Never commit a rendered manifest. `scripts/Deploy-Runtimes.ps1` renders into a
temporary directory, validates it with `agentrun runtime render`, applies it,
and deletes the temporary directory.

Deployment is intentionally split:

1. `Leaves` creates policy, research, and provider runtimes.
2. Copy the three A2A base URLs from AgentRun and verify each Agent Card.
3. Set `POLICY_A2A_URL`, `RESEARCH_A2A_URL`, and `PROVIDER_A2A_URL`.
4. `Concierge` creates the orchestration runtime.

`PUBLIC_BASE_URL` is optional. The application returns a dynamic Agent Card
using AgentRun's forwarded scheme/host/prefix headers. If an ingress does not
forward them correctly, set `PUBLIC_BASE_URL` explicitly in that runtime's
`spec.env` and apply a new version.

The CLI manifest schema does not currently expose AgentRun's **Tracing
Analysis** console switch. Enable it for all four runtimes in the AgentRun
console after the first deployment.

AgentRun may scale a downstream runtime to zero. Concierge therefore loads
Agent Cards with an explicit read timeout and bounded exponential retries.
Tune `A2A_DISCOVERY_TIMEOUT_SECONDS`, `A2A_DISCOVERY_MAX_ATTEMPTS`, and
`A2A_DISCOVERY_BACKOFF_SECONDS` only when measured cold-start latency requires
it; do not remove the bounds.
