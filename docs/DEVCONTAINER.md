# DevContainer for Agent Platform — E2E Agent Development

## Что это

DevContainer — контейнер с предустановленными инструментами для разработки и **E2E-верификации** агентного кода. Запускается в GitHub Codespaces или локально через Docker.

Конфигурация: `.devcontainer/devcontainer.json` в корне репозитория.

## Быстрый старт в Codespace

```bash
# 1. Создать codespace из репозитория
gh codespace create --repo videlboga/agent-platform --branch main --machine basicLinux32gb

# 2. Дождаться создания (30–60 секунд), получить имя
# Имя появится в stdout: "✔ codespace 'miniature-capybara' created"

# 3. SSH внутрь
gh codespace ssh --repo videlboga/agent-platform

# 4. После входа devcontainer автоматически выполнит postCreateCommand:
#    - pip install playwright pillow requests pixelmatch
#    - npx playwright install chromium
#    - mkdir -p /workspaces/agent-platform/screenshots/baseline
```

После установки можно сразу запускать E2E-скрипты (см. ниже).

## Что внутри

### Базовое окружение

| Компонент       | Версия | Назначение                     |
|-----------------|--------|--------------------------------|
| Python          | 3.12   | Язык агентных скриптов         |
| Node.js         | 20     | Playwright + pixelmatch CLI    |
| Playwright      | latest | Headless Chromium для скриншотов |
| Pillow          | latest | Обработка изображений (diff)   |
| pixelmatch      | latest | Попиксельное сравнение         |
| requests        | latest | HTTP-запросы к тестируемому API |

### E2E-инструменты в `scripts/`

- **`e2e-screenshot.py`** — скриншот страницы через Playwright + pixelmatch-дифф с baseline
- **`e2e-setup.sh`** — fallback-установщик (если postCreateCommand не отработал)
- **`deliver-artifact.sh`** — подготовка скриншота к отправке в Telegram/чат

## E2E-верификация: полный цикл

### 1. Запустить приложение

```bash
# В зависимости от проекта:
python app.py &
# или
docker compose up -d
# или
npm start &
```

Дождаться готовности:

```bash
curl -f http://localhost:PORT/health && echo "READY" || sleep 5
```

### 2. Сделать baseline-скриншот (первый раз или intentional change)

```bash
python scripts/e2e-screenshot.py \
  --url http://localhost:PORT/page \
  --output screenshots/baseline/page.png \
  --baseline screenshots/baseline/page.png \
  --viewport 1280,720 \
  --wait 2
```

> **Примечание:** При первом запуске baseline не существует — скрипт предупредит и создаст файл. Второй запуск уже будет сравнивать.

### 3. Сделать текущий скриншот с diff

```bash
python scripts/e2e-screenshot.py \
  --url http://localhost:PORT/page \
  --output screenshots/current/page.png \
  --baseline screenshots/baseline/page.png \
  --viewport 1280,720 \
  --wait 2
```

Если `diff > 5%` — скрипт завершится с exit 1 и создаст `page.png.diff.png`.

### 4. Проверить diff-изображение

```bash
ls -la screenshots/current/page.png.diff.png
```

### 5. Если изменения intentional — обновить baseline

```bash
cp screenshots/current/page.png screenshots/baseline/page.png
```

### 6. Подготовить артефакт для отправки

```bash
bash scripts/deliver-artifact.sh screenshots/current/page.png \
  "📸 Страница после фикса"
```

## Интеграция с агентной разработкой

DevContainer — это то, в чём агент (Hermes) проводит разработку и E2E-проверку кода.

### Жизненный цикл в agent-platform

```
Hermes получает задачу
  │
  ▼
Исследование кода (на сервере или в репозитории)
  │
  ▼
Создание Codespace (devcontainer конфигурирует окружение)
  │
  ▼
Разработка кода (branch → commit → push)
  │
  ▼
E2E-верификация:
  ├── Запуск приложения
  ├── Скриншот (Playwright)
  ├── Pixelmatch diff с baseline
  └── Результат → отчёт агенту
  │
  ▼
Создание PR → CI → Merge
  │
  ▼
Деплой на сервер → Удаление Codespace
```

### Guard-правила для E2E в агенте

1. **Не делать скриншоты прода** — только staging в Codespace
2. **Baseline хранится в репо** (`screenshots/baseline/`) — коммитится с кодом
3. **diff > 5%** — не merge без разбора
4. Для Telegram-ботов и не-web интерфейсов — E2E фаза пропускается

### Пример: агент проверяет UI-изменение

```bash
# Внутри Codespace (через SSH из агента)

# 1. Запуск приложения
python app.py &
sleep 3

# 2. Проверка через скриншот
python scripts/e2e-screenshot.py \
  --url http://localhost:8000 \
  --output screenshots/current/main.png \
  --baseline screenshots/baseline/main.png \
  --viewport 1280,720 \
  --wait 3

# 3. Проверка результата
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ Визуально без изменений"
else
  echo "⚠️ Обнаружены визуальные отличия!"
  bash scripts/deliver-artifact.sh \
    screenshots/current/main.png.diff.png \
    "🔍 Diff страницы после изменений"
fi
```

### Автоматическая установка

При создании Codespace `postCreateCommand` запускается автоматически. Если по какой-то причине он не сработал или ты открываешь контейнер вручную:

```bash
bash scripts/e2e-setup.sh
```

## Параметры `devcontainer.json`

| Параметр           | Значение                     | Зачем                     |
|--------------------|------------------------------|---------------------------|
| **image**          | `universal:2`                | Полноценный dev-образ     |
| **features**       | Python 3.12 + Node 20        | Языки скриптов            |
| **postCreateCommand** | Playwright + pixelmatch   | E2E-инструменты сразу     |
| **hostRequirements.memory** | 4GB                | Минимум для Chromium      |
| **extensions**     | Python, Pylance, GH Actions  | VSCode-опыт               |

## Pitfalls

### `~` в путях не работает

Hermes в subagent-режиме резолвит `~` в профильную песочницу, а не в домашнюю директорию Codespace. Всегда используй абсолютные пути (`/workspaces/agent-platform/...`) или относительные от `$CODESPACE_VSCODE_FOLDER`.

### Playwright требует Chromium

`npx playwright install chromium` в `postCreateCommand` устанавливает бинарник. Если команда не сработала:

```bash
npx playwright install chromium
# или
bash scripts/e2e-setup.sh
```

### Codespace гаснет через ~30 мин неактивности

Для долгих E2E-сессий увеличь idle timeout или делай heartbeat'ы:

```bash
gh api \
  -X PATCH \
  -H "Accept: application/vnd.github+json" \
  /user/codespaces/<NAME> \
  -f idle_timeout_minutes=120
```

### `postCreateCommand` не выполняется при rebuild

Только при первом создании. После rebuild — запустить вручную.

### diff > 5% может быть артефактом рендеринга

Шрифты, разница в версиях Chromium, антиалиасинг — могут давать 1–3% diff. Если diff стабильно 3% на каждом run — обнови baseline.

### Проверка что devcontainer работает

```bash
# Внутри Codespace
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright OK')"
python -c "from PIL import Image; print('✅ Pillow OK')"
python -c "import pixelmatch; print('✅ pixelmatch OK')"
```
