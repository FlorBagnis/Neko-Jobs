name: Monitor de empleos

on:
  schedule:
    - cron: "0 * * * *"   # cada hora
  workflow_dispatch:       # permite correrlo a mano desde la pestaña Actions

permissions:
  contents: write

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Buscar puestos nuevos
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          WHATSAPP_PHONE: ${{ secrets.WHATSAPP_PHONE }}
          CALLMEBOT_APIKEY: ${{ secrets.CALLMEBOT_APIKEY }}
        run: python monitor.py

      - name: Guardar estado
        run: |
          git config user.name "monitor-bot"
          git config user.email "monitor-bot@users.noreply.github.com"
          git add estado.json
          git diff --cached --quiet || (git commit -m "actualizar estado" && git push)
