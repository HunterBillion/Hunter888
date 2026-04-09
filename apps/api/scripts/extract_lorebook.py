"""Extract lorebook entries from character prompt .md files.

Reads each character prompt file and creates a standardized lorebook structure:
- card.json: core identity (always in prompt)
- entries.json: keyword-triggered lorebook entries
- examples.json: dialogue examples for RAG

This is a one-time extraction tool. Output goes to data/lorebook/{archetype}/.
After extraction, review and curate the JSON files manually.

Usage:
    python -m scripts.extract_lorebook [archetype]
    python -m scripts.extract_lorebook --all
"""

import json
import re
import sys
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "characters"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "lorebook"


def extract_sections(text: str) -> dict[str, str]:
    """Split markdown file into sections by ## headers."""
    sections = {}
    current_key = "header"
    current_lines = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def extract_legend(text: str) -> dict:
    """Extract structured data from the legend section."""
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- **"):
            match = re.match(r"- \*\*(.+?):\*\*\s*(.+)", line)
            if match:
                key = match.group(1).strip()
                val = match.group(2).strip()
                data[key] = val
    return data


def extract_phrases(text: str) -> list[dict]:
    """Extract emotion state phrases from the emotional states section."""
    examples = []
    current_emotion = None

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("### "):
            current_emotion = line[4:].strip().lower()
        elif re.match(r"^\d+\.\s+[«\"]", line) and current_emotion:
            # Extract quoted phrase
            phrase_match = re.search(r"[«\"](.+?)[»\"]", line)
            if phrase_match:
                examples.append({
                    "situation": f"Состояние {current_emotion}",
                    "dialogue": phrase_match.group(1),
                    "emotion": current_emotion,
                    "source": "extracted",
                })

    return examples


def extract_objections(text: str) -> list[dict]:
    """Extract objection entries from the objections section."""
    entries = []
    current_category = None
    current_phrases = []

    category_map = {
        "цена": "objection_price",
        "доверие": "objection_trust",
        "необходимость": "objection_necessity",
        "время": "objection_time",
        "конкуренты": "objection_competitor",
    }

    keyword_map = {
        "objection_price": ["дорого", "цена", "стоимость", "сколько", "оплата", "комиссия", "платить"],
        "objection_trust": ["гарантия", "обман", "доверие", "лицензия", "отзыв", "мошенники", "проверю"],
        "objection_necessity": ["не нужно", "зачем", "необходимость", "сам", "справлюсь"],
        "objection_time": ["время", "долго", "некогда", "ждать", "сроки"],
        "objection_competitor": ["другие", "конкуренты", "юрист", "бесплатно", "лучше"],
    }

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("### Категория"):
            # Save previous category
            if current_category and current_phrases:
                trait = None
                for key, val in category_map.items():
                    if key in line.lower() or (current_category and key in current_category.lower()):
                        trait = val
                        break
                if not trait and current_category:
                    for key, val in category_map.items():
                        if key in current_category.lower():
                            trait = val
                            break

            # Detect new category
            for key, val in category_map.items():
                if key in line.lower():
                    if current_category and current_phrases:
                        entries.append({
                            "trait_category": current_category,
                            "content": "Типичные возражения:\n" + "\n".join(f"- {p}" for p in current_phrases),
                            "keywords": keyword_map.get(current_category, []),
                            "priority": 8 if current_category in ("objection_price", "objection_trust") else 6,
                            "source": "extracted",
                        })
                    current_category = val
                    current_phrases = []
                    break
        elif re.match(r"^\d+\.", line) and current_category:
            phrase = re.sub(r"^\d+\.\s*", "", line).strip()
            if phrase.startswith("«") or phrase.startswith('"'):
                phrase = re.sub(r'^[«"]|[»"]$', "", phrase)
            current_phrases.append(phrase)

    # Don't forget last category
    if current_category and current_phrases:
        entries.append({
            "trait_category": current_category,
            "content": "Типичные возражения:\n" + "\n".join(f"- {p}" for p in current_phrases),
            "keywords": keyword_map.get(current_category, []),
            "priority": 8 if current_category in ("objection_price", "objection_trust") else 6,
            "source": "extracted",
        })

    return entries


def build_card(sections: dict, legend: dict, archetype_code: str) -> str:
    """Build the always-present character card from extracted data."""
    name = legend.get("ФИО", "Неизвестный персонаж")
    age = legend.get("Возраст", "")
    profession = legend.get("Профессия", "")
    family = legend.get("Семейное положение", "")

    # Extract character traits
    char_section = sections.get("характер", "")
    traits = []
    for line in char_section.splitlines():
        line = line.strip()
        if line.startswith("- **"):
            match = re.match(r"- \*\*(.+?):\*\*\s*(.+)", line)
            if match:
                traits.append(match.group(2).strip())

    traits_text = ". ".join(traits[:3]) if traits else ""

    # Build card
    card = f"Ты — {name}, {age}, {profession}."
    if family:
        card += f" {family}."

    # Debt info
    debt = legend.get("Итого", "")
    if not debt:
        # Try to find in structure
        for key, val in legend.items():
            if "итого" in key.lower():
                debt = val
                break
    if debt:
        card += f" Долг {debt}."

    card += f"\n\nХарактер: {traits_text}"
    card += "\n\nСтиль речи: разговорный, как по телефону. Без *(действий в скобках)*."
    card += " Эмоции через паузы (...), междометия, обрывы фраз."
    card += "\n\nТекущее состояние: {emotion_state}"

    return card


def extract_archetype(archetype_code: str, version: str = "v2") -> dict:
    """Extract one archetype into lorebook format."""
    # Find the file
    filename = f"{archetype_code}_{version}.md"
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        # Try v1
        filepath = PROMPTS_DIR / f"{archetype_code}_v1.md"
        if not filepath.exists():
            print(f"  SKIP: no file for {archetype_code}")
            return {}

    text = filepath.read_text(encoding="utf-8")
    sections = extract_sections(text)
    legend = extract_legend(sections.get("легенда", sections.get("header", "")))

    # Build card
    card = build_card(sections, legend, archetype_code)

    # Build entries
    entries = []

    # Financial situation from legend
    debt_lines = []
    for key, val in legend.items():
        if any(k in key.lower() for k in ["долг", "кредит", "банк", "мфо", "итого", "зарплата", "доход"]):
            debt_lines.append(f"{key}: {val}")
    if "структура долга" in sections.get("легенда", "").lower():
        # Extract debt structure from indented lines
        for line in sections.get("легенда", "").splitlines():
            line = line.strip()
            if line.startswith("- ") and any(k in line.lower() for k in ["банк", "мфо", "кредит", "займ", "итого"]):
                debt_lines.append(line[2:])

    if debt_lines:
        entries.append({
            "trait_category": "financial_situation",
            "content": "\n".join(debt_lines),
            "keywords": ["долг", "деньги", "кредит", "банк", "сумма", "платёж", "зарплата", "доход"],
            "priority": 9,
            "source": "extracted",
        })

    # Backstory from legend
    backstory = legend.get("Предыстория", "")
    if backstory:
        entries.append({
            "trait_category": "backstory",
            "content": backstory[:600],
            "keywords": ["история", "бизнес", "прошлое", "опыт", "раньше"],
            "priority": 7,
            "source": "extracted",
        })

    # Family from legend
    family = legend.get("Семейное положение", "")
    if family:
        entries.append({
            "trait_category": "family_context",
            "content": family,
            "keywords": ["семья", "жена", "муж", "дети", "дом", "квартира"],
            "priority": 7,
            "source": "extracted",
        })

    # Objections
    objections_text = sections.get("возражения", "")
    if objections_text:
        obj_entries = extract_objections(objections_text)
        entries.extend(obj_entries)

    # Breakpoint / tipping point
    breakpoint_text = sections.get("точка перелома", "")
    if breakpoint_text:
        entries.append({
            "trait_category": "breakpoint_trust",
            "content": breakpoint_text[:600],
            "keywords": ["доверие", "верю", "убедил", "согласен", "договор", "встреча"],
            "priority": 7,
            "source": "extracted",
        })

    # Traps / triggers
    traps_text = sections.get("ловушки для менеджера", sections.get("триггер отката", ""))
    if traps_text:
        entries.append({
            "trait_category": "emotional_triggers",
            "content": traps_text[:600],
            "keywords": ["манипуляция", "помогу", "не волнуйтесь", "оправдание", "скрипт"],
            "priority": 7,
            "source": "extracted",
        })

    # Behavior rules / decision drivers
    rules_text = sections.get("правила поведения", "")
    if rules_text:
        entries.append({
            "trait_category": "decision_drivers",
            "content": rules_text[:600],
            "keywords": ["решение", "думаю", "подумаю", "условия", "цифры"],
            "priority": 7,
            "source": "extracted",
        })

    # Speech examples from emotional states
    emotions_text = sections.get("эмоциональные состояния", "")
    examples = []
    if emotions_text:
        examples = extract_phrases(emotions_text)
        # Also create a speech_examples entry with one phrase per emotion
        summary_lines = []
        seen_emotions = set()
        for ex in examples:
            if ex["emotion"] not in seen_emotions and len(summary_lines) < 8:
                seen_emotions.add(ex["emotion"])
                summary_lines.append(f'{ex["emotion"].capitalize()}: "{ex["dialogue"][:80]}"')
        if summary_lines:
            entries.append({
                "trait_category": "speech_examples",
                "content": "Фразы по состояниям:\n" + "\n".join(summary_lines),
                "keywords": [],
                "priority": 5,
                "source": "extracted",
            })

    return {
        "card": card,
        "entries": entries,
        "examples": examples,
    }


def save_archetype(archetype_code: str, data: dict):
    """Save extracted data to JSON files."""
    out_dir = OUTPUT_DIR / archetype_code
    out_dir.mkdir(parents=True, exist_ok=True)

    # card.json
    with open(out_dir / "card.json", "w", encoding="utf-8") as f:
        json.dump({
            "archetype_code": archetype_code,
            "character_card": data["card"],
            "token_estimate": len(data["card"]) // 2,
        }, f, ensure_ascii=False, indent=2)

    # entries.json
    with open(out_dir / "entries.json", "w", encoding="utf-8") as f:
        json.dump(data["entries"], f, ensure_ascii=False, indent=2)

    # examples.json
    with open(out_dir / "examples.json", "w", encoding="utf-8") as f:
        json.dump(data["examples"], f, ensure_ascii=False, indent=2)

    print(f"  ✓ {archetype_code}: card={len(data['card'])}chars, entries={len(data['entries'])}, examples={len(data['examples'])}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "--all":
        archetype = sys.argv[1]
        data = extract_archetype(archetype)
        if data:
            save_archetype(archetype, data)
        return

    # Extract all
    seen = set()
    for f in sorted(PROMPTS_DIR.glob("*.md")):
        archetype = re.sub(r"_v\d+\.md$", "", f.name)
        if archetype in seen:
            continue
        seen.add(archetype)
        data = extract_archetype(archetype)
        if data:
            save_archetype(archetype, data)


if __name__ == "__main__":
    main()
