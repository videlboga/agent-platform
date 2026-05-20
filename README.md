# Agent Platform

Distributed AI agent dev infrastructure — runs on her own.

## Architecture

```
User
 ↓
Hermes Control Plane (85.9.211.227)
 ├── Postgres 16 (state, tasks)
 ├── Redis 7 (queue, pub/sub)
 ├── Model Router (ollama-cloud → copilot-acp → openrouter → openai-codex)
 └── GitHub Codespaces (isolated dev workspaces)
```

## Servers

| Server | IP | Role |
|--------|----|------|
| control | 85.9.211.227 | Control plane (Docker, PG, Redis) |
| proxy | 85.9.212.81 | External gateway (nginx, AWG, bot-v2) |

## Quick Start

```bash
# Connect to control-plane
ssh control

# Check services
docker compose -f /opt/agent-platform/docker-compose.yml ps
docker compose exec -T postgres pg_isready -U agent
docker compose exec -T redis redis-cli ping

# Create a dev workspace
gh codespace create --repo videlboga/agent-platform --branch main
gh codespace ssh --repo videlboga/agent-platform
```

## Git Flow

All work through PRs with CI checks:

```bash
git checkout -b feat/my-feature
# ... make changes ...
git add -A && git commit -m "feat: description"
git push -u origin HEAD
gh pr create --title "feat: description" --body "## Summary\n..."
```

CI: lint (YAML), validate (docker-compose, structure), markdown checks.

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — full MVP plan
- [GITHUB_SETUP.md](docs/GITHUB_SETUP.md) — CI/CD templates
