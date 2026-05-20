# GitHub Actions + Branch Protection — универсальный шаблон

Универсальный гайд для настройки CI/CD в любом проекте.
Адаптируй под свой стек, язык и структуру репозитория.

## 1. Структура workflows

```
.github/
└── workflows/
    ├── pr-review.yml    ← запускается на PR в main
    ├── ci.yml           ← запускается на push/PR в main
    └── deploy.yml       ← деплой (опционально, для agent-платформы)
```

## 2. PR-Review workflow

Создай `.github/workflows/pr-review.yml`:

```yaml
name: PR Review

on:
  pull_request:
    branches: [ main ]

jobs:
  lint-and-test:
    name: lint-and-test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up <LANG>
        uses: actions/setup-python@v5   # или setup-node, setup-go и т.д.
        with:
          python-version: '<VERSION>'    # 3.11, 3.12, 20.x, 1.22 и т.д.

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install flake8             # или eslint, golangci-lint и т.д.
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      - name: Run Linter
        run: |
          flake8 . \
            --exclude=<EXCLUDE_DIRS> \
            --count --select=E9,F63,F7 \
            --extend-ignore=<IGNORE_CODES> \
            --show-source --statistics
```

### Настройки под проект

| Параметр        | Python            | Node.js           | Go                |
|-----------------|-------------------|-------------------|--------------------|
| `<LANG>`        | python            | node              | go                 |
| `<VERSION>`     | 3.11              | 20.x              | 1.22               |
| Linter          | flake8            | eslint            | golangci-lint      |
| `<EXCLUDE_DIRS>`| .venv,archive     | node_modules,dist | vendor,.git        |
| `<IGNORE_CODES>`| F821,F823,F824    | (правила eslint)  | (правила linter)   |

Временные `--extend-ignore` — это техдолг. Запланируй задачу на удаление игноров.

## 3. CI workflow

Создай `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up <LANG>
        uses: actions/setup-python@v5
        with:
          python-version: '<VERSION>'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      - name: Run tests
        run: |
          PYTHONPATH=. pytest -q --ignore=<LEGACY_TESTS>
```

### Для не-Python проектов

```
Node.js:  npm ci && npm test
Go:       go test ./...
Rust:     cargo test
```

Сломанные легаси-тесты временно игнорируются через `--ignore=path`. Планируй починку.

## 4. Deploy workflow (для agent-платформы)

Создай `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  push:
    branches: [ main ]       # деплой только из main!
  workflow_dispatch:         # ручной запуск из UI

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production  # требует approval в GitHub Settings
    steps:
      - uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: deploy-runner
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /opt/projects/<PROJECT>
            git pull origin main
            docker compose up -d --build

      - name: Health check
        run: |
          curl -f --retry 5 --retry-delay 10 ${{ secrets.HEALTH_CHECK_URL }}
```

### Требования

- `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `HEALTH_CHECK_URL` — в GitHub Secrets
- Пользователь `deploy-runner` на целевом сервере (НЕ root)
- Docker Compose проект в `/opt/projects/<PROJECT>`
- Environment protection в Settings → Environments → production

## 5. Branch Protection

Создай `branch_protection.json`:

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["lint-and-test"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  },
  "restrictions": null
}
```

Примени через `gh` CLI:

```bash
gh api -X PUT /repos/OWNER/REPO/branches/main/protection \
  --input branch_protection.json
```

### Параметры

| Ключ                               | Что делает                                   |
|------------------------------------|----------------------------------------------|
| `required_approving_review_count`  | мин. число approval'ов (0 = без ревью)       |
| `enforce_admins`                   | применять ли protection к админам             |
| `contexts`                         | имена jobs, которые должны пройти перед merge|

## 6. Первый запуск — пошагово

```bash
# 1. Клонируй репо или перейди в существующее
cd ~/Projects/my-project

# 2. Создай директорию workflows
mkdir -p .github/workflows

# 3. Скопируй YAML-файлы в .github/workflows/

# 4. Создай ветку и запушь
git checkout -b chore/add-ci
git add .github/workflows/
git commit -m "chore(ci): add GitHub Actions workflows"
git push -u origin chore/add-ci

# 5. Создай PR
gh pr create \
  --title "chore(ci): add workflows" \
  --body "Добавлены PR lint, CI и deploy workflows."

# 6. Проверь что checks прошли в PR UI
# 7. После мёржа в main — примени branch protection
gh api -X PUT /repos/OWNER/REPO/branches/main/protection \
  --input branch_protection.json
```

## 7. Типичные ошибки и фиксы

| Симптом                                  | Причина                     | Решение                                  |
|------------------------------------------|-----------------------------|------------------------------------------|
| SyntaxError при линтинге                 | битый код                   | починить файл                            |
| F821 undefined name (массово)            | легаси без импортов         | добавить импорты или `--extend-ignore`   |
| Тесты падают на import collection        | тесты импортят несуществующие модули | `--ignore` или починить        |
| Deploy workflow не триггерится           | нет secrets в Settings      | добавить `DEPLOY_HOST`, `DEPLOY_SSH_KEY` |
| Branch protection не применяется         | нет прав admin              | проверить права на репо                  |

## 8. Что добавить потом

- `mypy` / `tsc` / статический анализ типов
- `pytest --maxfail=1 --disable-warnings`
- `docker build` + push to registry в CI (если Docker-проект)
- Notifications (Slack/Telegram) при фейле деплоя
- Matrix builds (несколько версий Python/Node)
- Dependabot для автообновления зависимостей
- Scheduled cleanup старых sandbox'ов (cron workflow)

## 9. Для agent-платформы — дополнительные workflows

### Sandbox cleanup (cron)

```yaml
name: Cleanup Sandboxes
on:
  schedule:
    - cron: '0 4 * * *'   # каждый день в 4:00 UTC
jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: Cleanup via deploy-runner
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: deploy-runner
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            docker container prune -f --filter "until=24h"
            docker image prune -f --filter "until=7d"
```

### Worker heartbeat check

```yaml
name: Worker Heartbeat
on:
  schedule:
    - cron: '*/5 * * * *'  # каждые 5 минут
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Check workers
        run: |
          for worker in dev-vps-1 dev-vps-2 home-pc-manjaro; do
            ssh -o ConnectTimeout=5 deploy-runner@$worker.internal "echo OK" \
              || echo "$worker DOWN" >> /tmp/status
          done
          if [ -f /tmp/status ]; then cat /tmp/status; exit 1; fi
```
