"""Shared Russian linguistic lexicons.

Single source of truth for word/phrase sets that more than one subsystem
needs to consume. Sprint 0 (2026-04-29) introduces this module to avoid
the alternative — a parallel YAML or a copy-paste of the same constants
into a new "AI-tell" file. Two sources for the same data drift; one source
does not.

Today's consumers:
  * ``app.services.nlp_cheat_detector`` (PvP cheat detection — pre-existing)
  * ``app.services.ai_tell_scrubber``   (call sentence-gate — Sprint 0 §5)

When a new consumer needs Russian linguistic markers, import from this
module rather than defining a private set. Adding a new phrase here
extends every consumer at once.

Why a plain module of ``frozenset`` constants and not a YAML/class:
  * Constants are introspectable by tests (AST + ``in`` checks).
  * No parsing layer = no bugs in the parsing layer.
  * A wrapper service can wrap *this* if a richer API is needed later.
"""

# ---------------------------------------------------------------------------
# Closed-class function words (kept for stylometry-style checks).
# ---------------------------------------------------------------------------

RUSSIAN_FUNCTION_WORDS: frozenset[str] = frozenset({
    "и", "в", "на", "но", "что", "это", "как", "то", "же", "ли", "бы",
    "по", "к", "со", "у", "от", "за", "из", "с", "до", "при", "над",
    "во", "же", "об", "через", "перед", "около", "среди", "между",
    "кроме", "вместо", "после", "прежде", "раньше", "позже", "всегда",
    "никогда", "иногда", "когда", "где", "куда", "откуда", "почему",
    "зачем", "как", "какой", "какая", "какие", "какое", "какого",
})

# Informal / colloquial markers — fillers, interjections, slang. The
# *opposite* signal of AI-tell phrases: when these appear the text reads
# more like spontaneous spoken Russian.
RUSSIAN_INFORMAL_MARKERS: frozenset[str] = frozenset({
    "ну", "блин", "типа", "короче", "ваще", "чё", "щас", "норм", "ок",
    "лол", "кек", "хз", "да", "ага", "нет", "угу", "ммм", "ааа", "ой",
    "ауч", "фух", "урра", "яй", "блин", "ёлки", "ёлки-палки",
})

# Connectives that essay-style writing leans on. Useful as a *signal*
# (high density → assistant register), NOT a hard block list — these
# words are also normal Russian.
RUSSIAN_TRANSITION_WORDS: frozenset[str] = frozenset({
    "однако", "кроме того", "во-первых", "во-вторых", "в-третьих",
    "следовательно", "таким образом", "итак", "в итоге", "в заключение",
    "с одной стороны", "с другой стороны", "в частности", "например",
    "то есть", "иными словами", "другими словами", "более того", "впрочем",
    "даже если", "в то время как", "несмотря на", "вопреки", "соответственно",
})

# AI-tell phrases — substrings whose presence in a *client persona* line
# during a sales-training call is a strong indicator the LLM has fallen
# back into "polite assistant" register. Each consumer picks its own
# matching strategy (case-fold + substring is the cheapest baseline).
#
# Provenance:
#   * lines 1-7  : carried over from nlp_cheat_detector v1 (PvP heuristic).
#   * lines 8-12 : seed list from product owner (Sprint 0 transcript review,
#                  2026-04-29). These are the phrases that "sound like AI"
#                  in the Hunter888 voice/call use case specifically.
#                  Refine via the golden_smoke auto-mining pass — do not
#                  expand by gut feel.
KNOWN_RUSSIAN_AI_PHRASES: frozenset[str] = frozenset({
    # 1-7 — PvP heuristic carry-over.
    "конечно", "безусловно", "отличный вопрос", "спасибо за вопрос",
    "давайте рассмотрим", "следует отметить", "в целом", "подводя итог",
    "как видно", "очевидно", "понятно", "несомненно",
    "представляется", "представляется интересным", "можно отметить",
    "стоит отметить", "важно подчеркнуть", "необходимо отметить",
    "принципиально важно", "позволяет утверждать",
    "приходится констатировать", "долженствует", "надлежит", "случается",
    # 8-12 — Sprint 0 product-owner seed.
    "давайте разберёмся", "давайте разберемся",
    "я понимаю ваш вопрос", "хороший вопрос",
    "как было сказано ранее",
})
