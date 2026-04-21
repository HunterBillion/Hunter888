#!/usr/bin/env bash
# scripts/setup-navy-tts.sh
#
# One-shot настройщик env на prod-сервере, который:
#   1. Prompt'ит новый (rotated) navy.api API key — БЕЗ эхо, без утечек.
#   2. Пишет правильный набор LOCAL_LLM_* + NAVY_TTS_* + LOCAL_EMBEDDING_*
#      в .env.production (с бэкапом предыдущего .env.production).
#   3. Делает ключ общим: один и тот же navy key для LLM + TTS + embeddings.
#   4. Перезапускает api контейнер, чтобы подхватить новые env.
#
# После запуска:
#   - LLM → https://api.navy/v1 с моделью claude-sonnet-4-20250514
#   - TTS → https://api.navy/v1/audio/speech (endpoint существует; модель
#     eleven_v3, голос "alice" — лучшее качество русского)
#   - Embeddings → https://api.navy/v1/embeddings с text-embedding-3-large
#
# Использование (на сервере):
#   cd /opt/hunter888
#   git pull
#   bash scripts/setup-navy-tts.sh
#
# Что делать если скрипт упал посередине:
#   cp .env.production.bak-<timestamp> .env.production
#   docker compose up -d api
#
set -euo pipefail

# --- 1. Preconditions --------------------------------------------------------

if [ ! -f .env.production ]; then
  echo "ERROR: .env.production не найден в $(pwd). Запусти из /opt/hunter888." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 не установлен (нужен для безопасной regex-замены)." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker не установлен." >&2
  exit 1
fi

# --- 2. Backup --------------------------------------------------------------

BACKUP=".env.production.bak-$(date +%Y%m%d-%H%M%S)"
cp .env.production "$BACKUP"
echo "✓ Backup: $BACKUP"

# --- 3. Prompt for rotated navy key (hidden input, no echo) -----------------

echo ""
echo "Впиши НОВЫЙ navy.api ключ (после ротации на https://api.navy/dashboard)."
echo "Ввод скрыт — ничего не появится на экране, это норма."
echo ""
printf "NAVY_API_KEY > "
stty -echo
read NAVY_KEY
stty echo
echo ""

if [ -z "$NAVY_KEY" ]; then
  echo "ERROR: пустой ключ, прерываю." >&2
  exit 1
fi

# Elementary sanity — just check format starts with sk-navy-
case "$NAVY_KEY" in
  sk-navy-*) : ;;
  *) echo "WARN: ключ не начинается с 'sk-navy-' — продолжаю всё равно, но проверь." >&2 ;;
esac

# --- 4. Rewrite .env.production via Python (safe for any special chars) ------

NAVY_KEY="$NAVY_KEY" python3 <<'PYEOF'
import os, re

key = os.environ["NAVY_KEY"]

# Every variable we touch. Comments → no effect; existing values get replaced
# in-place. If a key is missing entirely, we append it at the end.
targets = {
    # LLM via navy — unified gpt-5.4 (primary) + claude-opus-4.7 (fallback)
    "LOCAL_LLM_URL":         "https://api.navy/v1",
    "LOCAL_LLM_API_KEY":     key,
    "LOCAL_LLM_MODEL":       "gpt-5.4",
    "LLM_PRIMARY_MODEL":     "gpt-5.4",
    "LLM_FALLBACK_MODEL":    "claude-opus-4.7",
    "CLAUDE_MODEL":          "claude-opus-4.7",
    # TTS via navy — OpenAI tts-1-hd (works out of the box on navy, best
    # quality for Russian voice without needing ElevenLabs tier access).
    "NAVY_TTS_ENABLED":      "true",
    "NAVY_TTS_MODEL":        "tts-1-hd",
    "NAVY_TTS_VOICE":        "nova",
    # Turn off direct ElevenLabs: navy handles proxying
    "ELEVENLABS_ENABLED":    "false",
    # Embeddings via navy
    "LOCAL_EMBEDDING_URL":       "https://api.navy/v1",
    "LOCAL_EMBEDDING_API_KEY":   key,
    "LOCAL_EMBEDDING_MODEL":     "text-embedding-3-large",
}

with open(".env.production") as f:
    content = f.read()

for name, value in targets.items():
    pattern = rf"(?m)^{re.escape(name)}=.*$"
    if re.search(pattern, content):
        content = re.sub(pattern, f"{name}={value}", content)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += f"{name}={value}\n"

with open(".env.production", "w") as f:
    f.write(content)

print("✓ .env.production updated with navy.api configuration")
PYEOF

# --- 5. Show masked result --------------------------------------------------

echo ""
echo "--- .env.production (secrets masked) ---"
grep -E "^(LOCAL_LLM_|NAVY_TTS_|ELEVENLABS_ENABLED|LOCAL_EMBEDDING_)" .env.production | \
    sed -E 's/(KEY=)[^ ]+/\1****MASKED****/'
echo "----------------------------------------"

# --- 6. Restart api (docker compose will now read .env.production because the
#        prod override has explicit env_file: .env.production).
# We use -f to be explicit about which overlays are active.

echo ""
echo "Перезапускаю api..."
if [ -f docker-compose.prod.yml ]; then
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api
else
  docker compose up -d api
fi

sleep 8

# --- 7. Sanity check: look for validator errors in startup logs -------------

echo ""
echo "--- api startup (errors/critical/ready, last 60s) ---"
docker compose logs --since 60s api | grep -iE "ready|error|critical|validation|tts_provider" | tail -20 || true
echo "------------------------------------------------------"

echo ""
echo "Готово. Дальше:"
echo "  1) открой звонок: https://x-hunter.expert/training → Звонок → скажи что-то"
echo "  2) посмотри TTS-диагностику:"
echo "     docker compose logs --since 2m api | grep TTS_ | tail -20"
echo ""
echo "Если TTS_PROVIDERS показывает navy с правильным URL и TTS_SYNTH_FAIL нет —"
echo "звук работает. Если есть TTS_SYNTH_FAIL — покажи мне вывод."
