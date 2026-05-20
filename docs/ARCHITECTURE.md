# Agent Platform — Распределённая dev-инфраструктура

## Цель

Разработка на удалённых воркерах. Домашний ПК — опциональный.

## Архитектура

```
User
 ↓
Hermes Control Plane
 ├── Postgres (состояние, задачи)
 ├── Redis (очередь, event bus)
  ├── Model Router (ollama-cloud → copilot-acp → openrouter → openai-codex)
  ├── Workspace Manager (GitHub Codespaces — изолированные, не на проде)
 ├── GitHub / Gitea
 ├── Deploy Runner (отложено)
 └── Worker Registry (см. ниже)
```

## Серверы — текущие и целевые роли

| Сервер     | IP           | RAM   | Текущее                     | Целевая роль       |
|------------|--------------|-------|-----------------------------|---------------------|
| control    | 85.9.211.227 | 3.7GB | свежий, Ubuntu 26.04        | CONTROL-PLANE       |
| proxy      | 85.9.212.81  | 1.8GB | nginx, AWG, bot-v2          | внешний шлюз        |
| codespaces | —            | —     | GitHub Codespaces (Pro+)    | DEV-WORKERs (бесплатно) |
| bitrix1    | 85.9.210.113 | 0.8GB | bitrix_reports + Svobodacard| CLIENT-WORKER       |

## MVP — этапы

### 1. Control-plane VPS (85.9.211.227, 1 ядро, 3.7 GB RAM, 30 GB диск, UpCloud AMS)

Статус: ✅ куплен, Ubuntu 26.04, доступен по `ssh control`

```
/opt/agent-platform/
  docker-compose.yml    (hermes + postgres + redis)
  .env
  configs/
  logs/
  scripts/
  ssh/
  runners/
  projects/
```

### 2. Model Router (статус: ✅ базовая цепочка готова)

```yaml
model:
  provider: ollama-cloud
  default: deepseek-v4-pro

fallback_providers:
  - provider: copilot-acp
    model: gpt-4o
  - provider: openrouter
    model: google/gemini-2.5-flash
  # qwen-cli — OAuth сломан, баг на стороне Qwen (issue #4317)
  # openai-codex — добавить после hermes auth add openai-codex
```

**Проверенные провайдеры (20 мая 2026):**
- ollama-cloud → deepseek-v4-pro: ✓ работает, недельные лимиты
- copilot-acp → gpt-4o: ✓ Copilot CLI v1.0.48
- openrouter → gemini-2.5-flash: ✓ ключ обновлён
- openai-codex → gpt-5.1-codex: ✓ OAuth (hermes auth add)
- qwen-cli: ✗ баг на сервере Qwen (504, issue #4317)

**Итоговая цепочка:** ollama-cloud → copilot-acp → openrouter → openai-codex (4 уровня)

**Pitfall:** ollama-cloud при HTTP 429 НЕ переключается на fallback автоматически — Hermes не считает 429 не-retryable ошибкой. Мониторить лимиты или при утыкании переключать primary вручную.

### 3. Workspace (GitHub Codespaces)

Разработка идёт в изолированных GitHub Codespaces — **не на прод-серверах**.

GitHub Pro+ даёт 120 core-hours/мес бесплатно:
- **2-core** = 60 часов
- **4-core** = 30 часов

Codespace гаснет автоматически при неактивности (экономия лимита).

**Создание workspace под задачу:**

```bash
# Создать codespace из репо
gh codespace create --repo owner/repo --branch main --machine basicLinux32gb

# SSH внутрь
gh codespace ssh --repo owner/repo

# Удалить после задачи
gh codespace delete --repo owner/repo
```

**Сравнение с прошлым подходом:**

| Было (план) | Стало |
|-------------|-------|
| code-server на bestposts | GitHub Codespaces |
| 0.8GB RAM, делит с ботами | 2-4 core, изолирован |
| ручной docker run | `gh codespace create` |
| риски для прода | ноль рисков |
| платим за VPS | бесплатно в Pro+ |

**Требуется:** `gh auth login` (нужен GitHub-токен, scopes: `repo`, `codespace`)

### 4. Git-flow MVP

```
git clone → checkout -b agent/task-N → работа → commit → push → PR
```

### 5. Deploy Runner (позже)

Отдельно. Не в MVP.

## Worker Registry (черновик)

```yaml
workers:
  bestposts:
    host: bestposts
    capabilities: [docker, python, node, git]
    availability: persistent

  capalin:
    host: capalin
    capabilities: [docker, python, git]
    availability: persistent

  home-pc-manjaro:
    host: home-pc-manjaro.internal
    capabilities: [docker, gpu-optional, local-projects]
    availability: optional

  home-pc-windows:
    host: home-pc-windows.internal
    capabilities: [ue5, metahuman, powershell]
    availability: optional
```

## Безопасность

- agent-runner вместо root
- отдельные SSH-ключи на каждый worker
- deploy keys read-only
- .env не отдавать агентам целиком
- опасные команды подтверждать

## Правила (для Hermes)

1. Не работать в prod-каталогах
2. Всегда создавать ветку agent/task-N
3. Верифицировать результат (скриншот/exist/exit code)
4. Кириллические пути в wine — табу
5. Деплой только через deploy-runner, не напрямую
