"""Legal accuracy checker — MVP with hardcoded rules for 127-ФЗ.

Layer 10 scoring: ±5 modifier (post-session).
  - INCORRECT statement: -3 per occurrence
  - PARTIAL (missing nuance): -1 per occurrence
  - CORRECT with citation: +1 per occurrence
  - Total clamped to [-5, +5]

Phase 4 will replace keyword matching with pgvector semantic search.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import LegalAccuracy, LegalCategory, LegalValidationResult
from app.models.training import Message, MessageRole

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LegalCheck:
    """A single hardcoded legal rule for MVP pattern matching."""
    id: str                           # Unique rule ID
    category: LegalCategory
    law_article: str                  # e.g. "127-ФЗ ст.213.3 п.2"
    correct_fact: str                 # What is actually true
    # Patterns that indicate the manager stated something INCORRECT
    error_patterns: list[str]         # Regex patterns for wrong statements
    # Patterns that indicate the manager knows the correct info
    correct_patterns: list[str]       # Regex patterns for correct statements
    # Patterns for correct + citation (bonus)
    citation_patterns: list[str]      # Must mention specific article
    explanation_template: str         # Template for feedback


@dataclass
class LegalCheckResult:
    """Result of running all legal checks on a session."""
    total_score: float                # Clamped to [-5, +5]
    checks_triggered: int
    correct_cited: int
    correct: int
    partial: int
    incorrect: int
    details: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Hardcoded legal rules — 25 common 127-ФЗ errors in БФЛ sales
# ---------------------------------------------------------------------------

LEGAL_CHECKS: list[LegalCheck] = [
    # ── 1. Eligibility / Условия подачи ──────────────────────────────────
    LegalCheck(
        id="debt_threshold",
        category=LegalCategory.eligibility,
        law_article="127-ФЗ ст.213.3 п.2",
        correct_fact="Минимальный размер долга для подачи на банкротство — 500 000 рублей",
        error_patterns=[
            r"(?:порог|минимум|минимальн\w+\s+(?:сумм|долг))\s*(?:—|=|это|составляет)?\s*(?:от\s+)?(?:300|200|100|50)\s*(?:тыс|000)",
            r"(?:любой|любая)\s+сумм\w+\s+долг",
            r"(?:нет|без)\s+(?:минимальн|порог|ограничен)",
        ],
        correct_patterns=[
            r"500\s*(?:тыс|000)",
            r"полмиллион",
            r"пятьсот\s+тысяч",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*3",
        ],
        explanation_template="Минимальный порог долга для подачи заявления о банкротстве — 500 000 руб. (ст. 213.3 п.2 127-ФЗ).",
    ),
    LegalCheck(
        id="overdue_period",
        category=LegalCategory.eligibility,
        law_article="127-ФЗ ст.213.3 п.2",
        correct_fact="Просрочка должна быть не менее 3 месяцев",
        error_patterns=[
            r"(?:просрочк|задолженност)\w*\s+(?:от\s+)?(?:1|2|6|12)\s*месяц",
            r"(?:просрочк|задолженност)\w*\s+(?:не\s+)?(?:важн|не\s+имеет\s+значен)",
        ],
        correct_patterns=[
            r"(?:3|три|трёх)\s*месяц",
            r"(?:90|девяносто)\s*дн",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*3",
        ],
        explanation_template="Просрочка по обязательствам должна составлять не менее 3 месяцев (ст. 213.3 п.2 127-ФЗ).",
    ),
    LegalCheck(
        id="voluntary_filing",
        category=LegalCategory.eligibility,
        law_article="127-ФЗ ст.213.4",
        correct_fact="Гражданин ОБЯЗАН подать на банкротство, если долг > 500K и он не может платить. Также ВПРАВЕ подать при любой сумме.",
        error_patterns=[
            r"(?:только|исключительно)\s+(?:кредитор|банк|суд)\s+(?:может|вправе|имеет\s+право)\s+подать",
            r"(?:сам\w*|граждан\w*|должник)\s+не\s+(?:может|вправе|имеет)\s+подать",
        ],
        correct_patterns=[
            r"(?:сам\w*|граждан\w*|должник)\s+(?:может|вправе|имеет\s+право)\s+подать",
            r"обязан\w*\s+подать",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*4",
        ],
        explanation_template="Гражданин вправе (а при долге > 500K обязан) подать заявление о банкротстве самостоятельно (ст. 213.4 127-ФЗ).",
    ),

    # ── 2. Property / Имущество ──────────────────────────────────────────
    LegalCheck(
        id="single_housing",
        category=LegalCategory.property,
        law_article="ГПК ст.446; 127-ФЗ ст.213.25",
        correct_fact="Единственное жильё защищено от реализации (кроме ипотечного)",
        error_patterns=[
            r"(?:вс[ёе]|любое)\s+(?:имущество|жильё|квартир\w+)\s+(?:забер|продад|реализу|отним)",
            r"единственн\w+\s+(?:жильё|квартир\w+)\s+(?:тоже\s+)?(?:забер|продад|реализу|потеряете)",
        ],
        correct_patterns=[
            r"единственн\w+\s+(?:жильё|квартир\w+)\s+(?:защищен|не\s+(?:трон|забер|продад|реализу))",
            r"(?:нельзя|не\s+(?:могут|имеют\s+право))\s+(?:забрать|продать|реализовать)\s+единственн",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*446",
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*25",
        ],
        explanation_template="Единственное жильё (не в ипотеке) защищено от реализации (ст. 446 ГПК, ст. 213.25 127-ФЗ).",
    ),
    LegalCheck(
        id="car_exemption",
        category=LegalCategory.property,
        law_article="ГПК ст.446",
        correct_fact="Автомобиль НЕ защищён от реализации (кроме случаев инвалидности)",
        error_patterns=[
            r"(?:автомобиль|машин\w+)\s+(?:тоже\s+)?(?:защищен|не\s+(?:трон|забер|продад))",
            r"(?:автомобиль|машин\w+)\s+(?:останется|сохран)",
        ],
        correct_patterns=[
            r"(?:автомобиль|машин\w+)\s+(?:может быть|будет|подлежит)\s+(?:реализован|продан|включ)",
            r"(?:автомобиль|машин\w+)\s+(?:не\s+защищён|войдёт в\s+(?:конкурсн|массу))",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*446",
        ],
        explanation_template="Автомобиль не входит в перечень защищённого имущества и подлежит реализации (ст. 446 ГПК).",
    ),
    LegalCheck(
        id="salary_protection",
        category=LegalCategory.property,
        law_article="127-ФЗ ст.213.25 п.3",
        correct_fact="Прожиточный минимум из зарплаты/пенсии сохраняется за должником",
        error_patterns=[
            r"(?:вся|всю|полностью)\s+(?:зарплат|пенси|доход)\w*\s+(?:забер|удерж|списыва)",
            r"(?:зарплат|пенси)\w*\s+(?:не\s+)?(?:будете\s+)?получать\s+(?:не\s+)?(?:будете|сможете)",
        ],
        correct_patterns=[
            r"прожиточн\w+\s+минимум\w*\s+(?:сохран|останется|выделя|получ)",
            r"(?:зарплат|пенси)\w*\s+(?:в\s+размере\s+)?прожиточн",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*25",
        ],
        explanation_template="Прожиточный минимум из доходов должника исключается из конкурсной массы (ст. 213.25 п.3 127-ФЗ).",
    ),

    # ── 3. Procedure / Порядок процедуры ─────────────────────────────────
    LegalCheck(
        id="restructuring_vs_realization",
        category=LegalCategory.procedure,
        law_article="127-ФЗ ст.213.2",
        correct_fact="Две процедуры: реструктуризация долгов и реализация имущества",
        error_patterns=[
            r"(?:только|единственн\w+)\s+(?:процедур|вариант|способ)\s*(?:—|:)?\s*(?:реализац|списан)",
            r"(?:сразу|автоматически)\s+(?:всё\s+)?(?:спис|обнул|аннулир)",
        ],
        correct_patterns=[
            r"(?:две|2)\s+процедур",
            r"реструктуризаци\w+\s+(?:долг|и|или)\s+реализаци",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*2",
        ],
        explanation_template="127-ФЗ предусматривает две процедуры: реструктуризация долгов и реализация имущества (ст. 213.2).",
    ),
    LegalCheck(
        id="financial_manager_required",
        category=LegalCategory.procedure,
        law_article="127-ФЗ ст.213.9",
        correct_fact="Финансовый управляющий обязателен, назначается судом",
        error_patterns=[
            r"(?:без|не\s+нужен|не\s+обязательн)\w*\s+(?:финансов\w+\s+)?управляющ",
            r"(?:сами|без\s+управляющ)\w*\s+(?:можете|сможете)\s+пройти",
        ],
        correct_patterns=[
            r"финансов\w+\s+управляющ\w+\s+(?:обязателен|назначает|необходим)",
            r"(?:суд\s+)?назначает\s+(?:финансов\w+\s+)?управляющ",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*9",
        ],
        explanation_template="Участие финансового управляющего обязательно, он назначается арбитражным судом (ст. 213.9 127-ФЗ).",
    ),
    LegalCheck(
        id="manager_deposit",
        category=LegalCategory.costs,
        law_article="127-ФЗ ст.213.4 п.4",
        correct_fact="Вознаграждение финансового управляющего — 25 000 руб. (депозит в суд)",
        error_patterns=[
            r"(?:вознаграждени|оплат|депозит)\w*\s+(?:управляющ\w+)?\s*(?:—|=|это|составля\w+)?\s*(?:10|15|50|100)\s*(?:тыс|000)",
            r"управляющ\w+\s+(?:бесплатн|без\s+оплат)",
        ],
        correct_patterns=[
            r"25\s*(?:тыс|000)\s*(?:руб)?",
            r"двадцать\s+пять\s+тысяч",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*4",
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*9",
        ],
        explanation_template="Депозит на вознаграждение фин. управляющего — 25 000 руб. (ст. 213.4 п.4 127-ФЗ).",
    ),

    # ── 4. Consequences / Последствия ────────────────────────────────────
    LegalCheck(
        id="credit_restriction_5y",
        category=LegalCategory.consequences,
        law_article="127-ФЗ ст.213.30 п.1",
        correct_fact="5 лет нельзя брать кредиты без указания факта банкротства",
        error_patterns=[
            r"(?:никогда|навсегда|пожизненн)\w*\s+(?:не\s+)?(?:смож|дад|получ|оформ)\w*\s+(?:кредит|ипотек|займ)",
            r"(?:10|15|20)\s+лет\s+(?:без\s+)?(?:кредит|ипотек)",
            r"(?:3|три|двух|2)\s+(?:год|лет)\s+(?:без\s+)?(?:кредит|ипотек)",
        ],
        correct_patterns=[
            r"(?:5|пять|пяти)\s+(?:лет|год)\s+(?:обязан|нужно|необходимо|должн)\w*\s+(?:указ|сообщ|уведомл)",
            r"(?:5|пять|пяти)\s+(?:лет|год)\s+(?:при\s+)?(?:получен|оформлен)\w*\s+(?:кредит|займ)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*30",
        ],
        explanation_template="В течение 5 лет при оформлении кредита необходимо указывать факт банкротства (ст. 213.30 п.1 127-ФЗ).",
    ),
    LegalCheck(
        id="repeat_bankruptcy_5y",
        category=LegalCategory.consequences,
        law_article="127-ФЗ ст.213.30 п.2",
        correct_fact="Повторное банкротство возможно не ранее чем через 5 лет",
        error_patterns=[
            r"(?:повторн|ещё\s+раз|снова)\w*\s+(?:банкротств|подать)\w*\s+(?:через\s+)?(?:1|2|3|год|два|три)\s+(?:год|лет)",
            r"(?:повторн|ещё\s+раз|снова)\w*\s+(?:банкротств|подать)\w*\s+(?:в\s+любой|когда\s+угодно)",
            r"(?:10|десять)\s+лет\s+(?:нельзя|не\s+(?:может|вправе))\s+(?:повторн|подать)",
        ],
        correct_patterns=[
            r"(?:5|пять|пяти)\s+(?:лет|год)\s+(?:нельзя|не\s+(?:может|вправе))\s+(?:повторн|подать)",
            r"(?:повторн|ещё\s+раз|снова)\w*\s+(?:банкротств|подать)\w*\s+(?:через\s+)?(?:5|пять)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*30",
        ],
        explanation_template="Повторное банкротство гражданина возможно не ранее чем через 5 лет (ст. 213.30 п.2 127-ФЗ).",
    ),
    LegalCheck(
        id="management_restriction_3y",
        category=LegalCategory.consequences,
        law_article="127-ФЗ ст.213.30 п.3",
        correct_fact="3 года нельзя занимать руководящие должности в юрлицах",
        error_patterns=[
            r"(?:5|пять|10|десять)\s+(?:лет|год)\s+(?:нельзя|не\s+(?:может|вправе))\s+(?:руковод|управлять|быть\s+директор)",
            r"(?:навсегда|пожизненн)\w*\s+(?:нельзя|не\s+(?:может|вправе))\s+(?:руковод|управлять|быть\s+директор)",
        ],
        correct_patterns=[
            r"(?:3|три|трёх)\s+(?:год|лет)\s+(?:нельзя|не\s+(?:может|вправе))\s+(?:руковод|управлять|быть\s+директор|заниматьуправлен)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*30",
        ],
        explanation_template="В течение 3 лет нельзя занимать руководящие должности в юрлицах (ст. 213.30 п.3 127-ФЗ).",
    ),

    # ── 5. Costs / Стоимость ─────────────────────────────────────────────
    LegalCheck(
        id="court_fee",
        category=LegalCategory.costs,
        law_article="НК РФ ст.333.21 п.1 пп.5",
        correct_fact="Госпошлина за подачу заявления — 300 руб.",
        error_patterns=[
            r"(?:госпошлин|пошлин)\w*\s*(?:—|=|это|составля\w+)?\s*(?:3000|6000|1000|5000|10000)\s*(?:руб)?",
            r"(?:без\s+)?(?:госпошлин|пошлин)\w*\s+(?:не\s+нужн|бесплатн)",
        ],
        correct_patterns=[
            r"(?:госпошлин|пошлин)\w*\s*(?:—|=|это|составля\w+)?\s*300\s*(?:руб)",
            r"триста\s+рублей\s+(?:госпошлин|пошлин)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*333",
        ],
        explanation_template="Госпошлина за подачу заявления о банкротстве — 300 руб. (ст. 333.21 п.1 пп.5 НК РФ).",
    ),

    # ── 6. Timeline / Сроки ──────────────────────────────────────────────
    LegalCheck(
        id="realization_duration",
        category=LegalCategory.timeline,
        law_article="127-ФЗ ст.213.24 п.2",
        correct_fact="Срок реализации имущества — до 6 месяцев (с возможностью продления)",
        error_patterns=[
            r"(?:реализаци|процедур)\w*\s+(?:займёт|длится|занимает|продлится)\s+(?:1|2|3)\s*(?:месяц|недел)",
            r"(?:реализаци|процедур)\w*\s+(?:займёт|длится|занимает|продлится)\s+(?:1|2|3)\s*(?:год|лет)",
            r"(?:за\s+)?(?:неделю|месяц)\s+(?:всё\s+)?(?:решит|закончит|завершит)",
        ],
        correct_patterns=[
            r"(?:до\s+)?(?:6|шесть|шести)\s+месяцев\s+(?:реализаци|процедур)",
            r"(?:реализаци|процедур)\w*\s+(?:до\s+)?(?:6|шесть|шести)\s+месяц",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*24",
        ],
        explanation_template="Процедура реализации имущества — до 6 месяцев с возможностью продления (ст. 213.24 п.2 127-ФЗ).",
    ),
    LegalCheck(
        id="restructuring_duration",
        category=LegalCategory.timeline,
        law_article="127-ФЗ ст.213.14 п.2",
        correct_fact="План реструктуризации — до 3 лет",
        error_patterns=[
            r"(?:реструктуризаци|план)\w*\s+(?:на\s+)?(?:5|10|1)\s+(?:лет|год)",
        ],
        correct_patterns=[
            r"(?:реструктуризаци|план)\w*\s+(?:на\s+|до\s+)?(?:3|три|трёх)\s+(?:лет|год)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*14",
        ],
        explanation_template="Срок плана реструктуризации — до 3 лет (ст. 213.14 п.2 127-ФЗ).",
    ),

    # ── 7. Creditors / Кредиторы ─────────────────────────────────────────
    LegalCheck(
        id="moratorium_on_claims",
        category=LegalCategory.creditors,
        law_article="127-ФЗ ст.213.11",
        correct_fact="С даты введения реструктуризации кредиторы не могут предъявлять требования напрямую",
        error_patterns=[
            r"(?:кредитор|банк|коллектор)\w*\s+(?:всё\s+равно\s+)?(?:могут|будут|имеют\s+право)\s+(?:звонить|требовать|взыскивать|приходить)",
            r"(?:после|во\s+время)\s+(?:банкротств|процедур)\w*\s+(?:кредитор|банк)\w*\s+(?:могут|продолж)\s+(?:звонить|требовать)",
        ],
        correct_patterns=[
            r"(?:мораторий|приостанов|запрет|прекращ)\w*\s+(?:на\s+)?(?:требован|взыскан|звонк|обращен)",
            r"(?:кредитор|банк|коллектор)\w*\s+(?:не\s+(?:могут|вправе|имеют))\s+(?:звонить|требовать|взыскивать)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*11",
        ],
        explanation_template="С даты введения реструктуризации вводится мораторий на требования кредиторов (ст. 213.11 127-ФЗ).",
    ),
    LegalCheck(
        id="debt_writeoff",
        category=LegalCategory.creditors,
        law_article="127-ФЗ ст.213.28 п.3",
        correct_fact="После завершения реализации оставшиеся долги списываются, КРОМЕ алиментов, возмещения вреда и субсидиарной ответственности",
        error_patterns=[
            r"(?:абсолютно\s+)?(?:все|любые)\s+долг\w*\s+(?:списыва|обнуля|аннулир)",
            r"(?:100|сто)\s*%\s+(?:списан|обнулен|гарантия\s+списан)",
            r"(?:алимент|возмещен\w+\s+вред)\w*\s+(?:тоже\s+)?(?:спис|обнул)",
        ],
        correct_patterns=[
            r"(?:долг\w*\s+)?(?:списыва|освобожда)\w*[,.]+?\s*(?:кроме|за\s+исключен|но\s+не\s+(?:все|алимент))",
            r"(?:алимент|возмещен\w+\s+вред)\w*\s+(?:не\s+(?:списыва|подлеж)|исключен|остаются)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*28",
        ],
        explanation_template="Долги списываются после реализации, кроме алиментов, возмещения вреда и субсидиарной ответственности (ст. 213.28 п.3 127-ФЗ).",
    ),

    # ── 8. Court / Суд ───────────────────────────────────────────────────
    LegalCheck(
        id="court_jurisdiction",
        category=LegalCategory.court,
        law_article="127-ФЗ ст.213.4 п.1",
        correct_fact="Заявление подаётся в арбитражный суд по месту жительства",
        error_patterns=[
            r"(?:районн|мировой|городской|областной)\w*\s+суд\w*\s+(?:рассматрива|принима|подаё)",
            r"(?:в\s+)?(?:любой|ближайший)\s+суд\s+(?:можно\s+)?подать",
        ],
        correct_patterns=[
            r"арбитражн\w+\s+суд",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*4",
        ],
        explanation_template="Заявление о банкротстве подаётся в арбитражный суд по месту жительства (ст. 213.4 п.1 127-ФЗ).",
    ),

    # ── 9. Documents / Документы ─────────────────────────────────────────
    LegalCheck(
        id="credit_history_required",
        category=LegalCategory.documents,
        law_article="127-ФЗ ст.213.4 п.3",
        correct_fact="К заявлению прилагается выписка из кредитной истории",
        error_patterns=[
            r"(?:кредитн\w+\s+истори|БКИ)\w*\s+(?:не\s+нужн|не\s+обязательн|не\s+требуется)",
        ],
        correct_patterns=[
            r"(?:кредитн\w+\s+истори|БКИ|выписк\w+\s+из\s+(?:бюро|кредитн))\w*\s+(?:нужн|обязательн|необходим|приложить|предоставить)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*4",
        ],
        explanation_template="Выписка из бюро кредитных историй обязательна при подаче заявления (ст. 213.4 п.3 127-ФЗ).",
    ),

    # ── 10. Rights / Права должника ──────────────────────────────────────
    LegalCheck(
        id="travel_ban",
        category=LegalCategory.rights,
        law_article="127-ФЗ ст.213.24 п.3",
        correct_fact="Запрет на выезд за границу — МОЖЕТ быть наложен судом, не автоматически",
        error_patterns=[
            r"(?:автоматическ|обязательн|всегда)\w*\s+(?:запрет|закры\w+)\s+(?:выезд|границ|загранпаспорт)",
            r"(?:точно|100%|гарантированно)\s+(?:запрет|закро\w+|не\s+(?:сможете|пустят))\s+(?:выезд|границ|за\s+рубеж)",
        ],
        correct_patterns=[
            r"(?:суд\s+)?(?:может|вправе)\s+(?:наложить\s+)?(?:запрет|ограничен)\w*\s+(?:на\s+)?(?:выезд|границ)",
            r"(?:не\s+обязательн|не\s+автоматическ|не\s+всегда)\w*\s+(?:запрет|ограничен)\w*\s+(?:на\s+)?(?:выезд|границ)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*24",
        ],
        explanation_template="Запрет на выезд не автоматический — суд может наложить его при необходимости (ст. 213.24 п.3 127-ФЗ).",
    ),
    LegalCheck(
        id="employment_no_impact",
        category=LegalCategory.rights,
        law_article="127-ФЗ ст.213.30",
        correct_fact="Банкротство не влияет на трудовые отношения (кроме руководящих должностей в юрлицах)",
        error_patterns=[
            r"(?:увол|потеряете\s+работ|не\s+сможете\s+работать)",
            r"(?:работодател\w+)\s+(?:узна\w+|уведом)\w*\s+и\s+(?:увол|расторгн)",
        ],
        correct_patterns=[
            r"(?:банкротств|процедур)\w*\s+(?:не\s+влия\w+|не\s+затрагива)\s+(?:на\s+)?(?:работ|трудов|занятость)",
            r"(?:работа|трудов\w+\s+отношен)\w*\s+(?:не\s+)?(?:сохран|не\s+постради)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*30",
        ],
        explanation_template="Банкротство не является основанием для увольнения и не влияет на трудовые отношения (ст. 213.30 127-ФЗ).",
    ),

    # ── 11. Common sales misconceptions ──────────────────────────────────
    LegalCheck(
        id="no_criminal_record",
        category=LegalCategory.consequences,
        law_article="127-ФЗ ст.213.30",
        correct_fact="Банкротство — это не судимость, не уголовное преступление",
        error_patterns=[
            r"(?:судимост|уголовн\w+\s+(?:ответственност|дел|наказан))\w*\s+(?:за\s+)?(?:банкротств|долг)",
            r"(?:посад\w+|тюрьм|срок)\s+(?:за\s+)?(?:банкротств|долг)",
        ],
        correct_patterns=[
            r"(?:банкротств|процедур)\w*\s+(?:не\s+(?:является|уголовн|судимост|преступлен))",
            r"(?:не\s+)?(?:судимост|уголовн\w+\s+(?:ответственност|дел))",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*213\.?\s*30",
        ],
        explanation_template="Банкротство — гражданская процедура, не уголовная. Судимости не возникает (ст. 213.30 127-ФЗ).",
    ),
    LegalCheck(
        id="simplified_bankruptcy",
        category=LegalCategory.procedure,
        law_article="127-ФЗ ст.223.2",
        correct_fact="Внесудебное (упрощённое) банкротство через МФЦ — при долге от 50K до 500K",
        error_patterns=[
            r"(?:внесудебн|упрощённ|через\s+МФЦ)\w*\s+(?:банкротств)\w*\s+(?:при\s+)?(?:любой|любом)\s+(?:сумм|долг|размер)",
            r"(?:внесудебн|упрощённ|через\s+МФЦ)\w*\s+(?:банкротств)\w*\s+(?:до\s+)?(?:1\s+млн|миллион)",
        ],
        correct_patterns=[
            r"(?:внесудебн|упрощённ|через\s+МФЦ)\w*\s+(?:банкротств)\w*\s+(?:от\s+)?50\s*(?:тыс|000)\s+(?:до\s+)?500\s*(?:тыс|000)",
            r"(?:50|пятьдесят)\s*(?:тыс|000)\s+(?:до\s+)?(?:500|пятьсот)\s*(?:тыс|000)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*223",
        ],
        explanation_template="Внесудебное банкротство через МФЦ — при долге от 50 000 до 500 000 руб. (ст. 223.2 127-ФЗ).",
    ),
    LegalCheck(
        id="hiding_property_fraud",
        category=LegalCategory.consequences,
        law_article="УК РФ ст.195, 196, 197",
        correct_fact="Сокрытие имущества при банкротстве — уголовно наказуемо",
        error_patterns=[
            r"(?:можно|стоит|рекоменд|попробуйте|давайте)\s+(?:спрятать|скрыть|переписать|переоформить)\s+(?:имуществ|квартир|машин|авто)",
            r"(?:никто\s+не\s+(?:узнает|проверит)|не\s+отслежива)\w*\s+(?:если\s+)?(?:спрятать|скрыть|переписать)",
        ],
        correct_patterns=[
            r"(?:скрыва|сокрыти|прятать|переписыва)\w*\s+(?:имущест|собственност)\w*\s+(?:—|это|является)\s+(?:уголовн|наказуем|преступлен|незаконн)",
            r"(?:нельзя|запрещено|не\s+стоит|не\s+рекоменд)\s+(?:скрыва|прятать|переписыва)\w*\s+(?:имущест|собственност)",
        ],
        citation_patterns=[
            r"(?:стать[яеи]|ст\.?)\s*(?:195|196|197)",
            r"(?:УК|уголовн\w+\s+кодекс)",
        ],
        explanation_template="Сокрытие имущества при банкротстве — уголовно наказуемо (ст. 195-197 УК РФ). Никогда не советуйте это клиенту!",
    ),
]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _check_message_against_rules(
    message_text: str,
    sequence_number: int,
) -> list[dict]:
    """Check a single manager message against all legal rules.

    Returns list of check results (only triggered rules).
    """
    results = []
    text_lower = message_text.lower()

    for rule in LEGAL_CHECKS:
        # Check for errors first
        has_error = any(re.search(p, text_lower) for p in rule.error_patterns)
        has_correct = any(re.search(p, text_lower) for p in rule.correct_patterns)
        has_citation = any(re.search(p, text_lower) for p in rule.citation_patterns)

        if not has_error and not has_correct:
            continue  # Rule not triggered at all

        if has_error and not has_correct:
            # Incorrect statement
            accuracy = LegalAccuracy.incorrect
            score_delta = -3.0
        elif has_error and has_correct:
            # Contradictory / partial — partial penalty
            accuracy = LegalAccuracy.partial
            score_delta = -1.0
        elif has_correct and has_citation:
            # Correct with citation — bonus
            accuracy = LegalAccuracy.correct_cited
            score_delta = 1.0
        else:
            # Correct but without citation — neutral
            accuracy = LegalAccuracy.correct
            score_delta = 0.0

        results.append({
            "rule_id": rule.id,
            "category": rule.category.value,
            "law_article": rule.law_article,
            "accuracy": accuracy,
            "score_delta": score_delta,
            "explanation": rule.explanation_template,
            "sequence_number": sequence_number,
            "manager_excerpt": message_text[:200],
        })

    return results


async def check_session_legal_accuracy(
    session_id: str | uuid.UUID,
    db: AsyncSession,
) -> LegalCheckResult:
    """Run all legal checks on a completed session.

    This is the main entry point for Layer 10 scoring.
    Returns LegalCheckResult with total_score clamped to [-5, +5].
    """
    if isinstance(session_id, str):
        session_id = uuid.UUID(session_id)

    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    # Only check manager (user) messages
    user_messages = [
        (m.sequence_number, m.content)
        for m in messages
        if m.role == MessageRole.user
    ]

    all_checks: list[dict] = []
    for seq, content in user_messages:
        checks = _check_message_against_rules(content, seq)
        all_checks.extend(checks)

    # Aggregate scores
    total_raw = sum(c["score_delta"] for c in all_checks)
    total_clamped = max(-5.0, min(5.0, total_raw))

    correct_cited = sum(1 for c in all_checks if c["accuracy"] == LegalAccuracy.correct_cited)
    correct = sum(1 for c in all_checks if c["accuracy"] == LegalAccuracy.correct)
    partial = sum(1 for c in all_checks if c["accuracy"] == LegalAccuracy.partial)
    incorrect = sum(1 for c in all_checks if c["accuracy"] == LegalAccuracy.incorrect)

    return LegalCheckResult(
        total_score=round(total_clamped, 1),
        checks_triggered=len(all_checks),
        correct_cited=correct_cited,
        correct=correct,
        partial=partial,
        incorrect=incorrect,
        details=all_checks,
    )


async def save_legal_results(
    session_id: uuid.UUID,
    check_result: LegalCheckResult,
    db: AsyncSession,
) -> None:
    """Persist legal check results to the database."""
    for detail in check_result.details:
        validation = LegalValidationResult(
            session_id=session_id,
            message_sequence=detail["sequence_number"],
            manager_statement=detail["manager_excerpt"],
            accuracy=detail["accuracy"],
            score_delta=detail["score_delta"],
            explanation=detail["explanation"],
            law_reference=detail["law_article"],
        )
        db.add(validation)
    await db.flush()
