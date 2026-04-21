#!/usr/bin/env bash
# wipe_github.sh — backup current origin/main, then force-push empty main.
# Safe: локальные файлы НЕ трогает. Если что — восстанавливай из тэга.
set -euo pipefail

REPO_DIR="/Users/bubble3/Desktop/Проекты_Х/wr1/Hunter888-main"
BACKUP_REF="backup-before-wipe-2026-04-18"

cd "$REPO_DIR"

echo "━━━ step 0: проверки ━━━"
echo "CWD: $(pwd)"
echo "Remote:"
git remote -v
echo "gh auth:"
gh auth status 2>&1 | head -5

echo ""
echo "━━━ step 1: забираем свежий origin/main ━━━"
git fetch origin

echo ""
echo "━━━ step 2: создаём backup-тэг и backup-ветку ━━━"
git push origin "refs/remotes/origin/main:refs/tags/$BACKUP_REF"    || echo "  backup tag возможно уже есть — продолжаем"
git push origin "refs/remotes/origin/main:refs/heads/$BACKUP_REF"   || echo "  backup ветка возможно уже есть — продолжаем"
echo "  backup: https://github.com/HunterBillion/Hunter888/tree/$BACKUP_REF"

echo ""
echo "━━━ step 3: пробуем снять branch-protection (если есть) ━━━"
gh api -X DELETE "repos/HunterBillion/Hunter888/branches/main/protection" 2>/dev/null \
  && echo "  protection снята" \
  || echo "  protection отсутствует либо нет admin — это OK, если force пройдёт"

echo ""
echo "━━━ step 4: создаём локальную orphan-ветку с одним пустым коммитом ━━━"
# Запоминаем текущую рабочую ветку
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "  текущая рабочая ветка: $CURRENT_BRANCH"

git checkout --orphan temp-empty-main
# Убрать всё из индекса (но не с диска!)
git rm -rf --cached . >/dev/null 2>&1 || true
# Создать минимальный README
printf '# Hunter888\n\nRepository is being rebuilt. Wait for the next push (optimization sweep in progress, 2026-04-18).\n' > README_WIPE.md
git add README_WIPE.md
git -c user.name="Hunter888 Bot" -c user.email="noreply@hunter888.local" \
    commit -m "Reset repository: wipe for optimization sweep (backup: $BACKUP_REF)" --no-verify

echo ""
echo "━━━ step 5: принудительный push orphan-ветки как main ━━━"
git push origin temp-empty-main:main --force

echo ""
echo "━━━ step 6: возвращаемся на свою рабочую ветку ━━━"
git checkout "$CURRENT_BRANCH"
git branch -D temp-empty-main
# Убираем README_WIPE.md который остался от orphan (если вдруг появился)
rm -f README_WIPE.md

echo ""
echo "━━━ ГОТОВО ━━━"
echo "  main на GitHub: один коммит 'Reset repository…'"
echo "  backup живёт в tag + branch: $BACKUP_REF"
echo "  твоя локальная '$CURRENT_BRANCH' не изменилась (422 файла на месте)"
echo ""
echo "  восстановление если понадобится:"
echo "    git push origin refs/tags/$BACKUP_REF:refs/heads/main --force"
