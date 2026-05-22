# Baseline Screenshots

Эта папка содержит **эталонные скриншоты** для визуального сравнения при e2e-тестах.

## Формат

- PNG, именованные по смыслу: `homepage.png`, `login-form.png`, `settings-page.png`
- Желательно 1280×720 (дефолтный viewport в e2e-screenshot.py)
- Создаются вручную при первом запуске: `pip install playwright && python3 scripts/e2e-screenshot.py --url http://... --output screenshots/baseline/page.png`

## Обновление

Когда UI меняется намеренно:
```bash
# Удалить старый baseline
rm screenshots/baseline/page.png
# Сделать новый
python3 scripts/e2e-screenshot.py --url http://... --output screenshots/baseline/page.png
# Закоммитить
git add screenshots/baseline/page.png && git commit -m "screenshots: update homepage baseline"
```
