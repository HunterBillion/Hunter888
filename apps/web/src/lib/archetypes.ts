import type { ArchetypeCode, ArchetypeGroup, ArchetypeTier, BehaviorTag, SkillCode } from "@/types";

// ─── Extended ArchetypeInfo Interface ────────────────────────────────────────

export interface ArchetypeInfo {
  code: ArchetypeCode;
  name: string;
  subtitle: string;
  description: string;
  detailed_behavior: string;
  group: ArchetypeGroup;
  tier: ArchetypeTier;
  difficulty: number;
  unlock_level: number;
  color: string;
  icon: string;
  tags: BehaviorTag[];
  counters: SkillCode[];
  weakness: string;
}

// ─── Group Definitions ──────────────────────────────────────────────────────

export interface ArchetypeGroupInfo {
  label: string;
  color: string;
  icon: string;
  description: string;
  key_skills: SkillCode[];
}

export const ARCHETYPE_GROUPS: Record<ArchetypeGroup, ArchetypeGroupInfo> = {
  resistance: {
    label: "Сопротивление",
    color: "var(--accent)",
    icon: "СП",
    description: "Активно противостоят менеджеру. Сражаются, не убегают.",
    key_skills: ["stress_resistance", "objection_handling"],
  },
  emotional: {
    label: "Эмоциональные",
    color: "var(--accent)",
    icon: "ЭМ",
    description: "Захлёстнуты эмоциями. Не сопротивляются — тонут.",
    key_skills: ["empathy", "rapport_building"],
  },
  control: {
    label: "Контроль",
    color: "var(--accent)",
    icon: "КТ",
    description: "Хотят контролировать разговор и менеджера.",
    key_skills: ["knowledge", "objection_handling", "legal_knowledge"],
  },
  avoidance: {
    label: "Избегание",
    color: "var(--accent)",
    icon: "ИЗ",
    description: "Не хотят решать проблему. Молчат, переносят, \"думают\".",
    key_skills: ["rapport_building", "closing", "time_management"],
  },
  special: {
    label: "Особые",
    color: "var(--accent)",
    icon: "ОС",
    description: "Ситуационные архетипы с уникальной механикой.",
    key_skills: ["adaptation", "rapport_building"],
  },
  cognitive: {
    label: "Когнитивные",
    color: "var(--accent)",
    icon: "КГ",
    description: "Особенности восприятия и мышления. По-другому обрабатывают информацию.",
    key_skills: ["adaptation", "knowledge", "empathy"],
  },
  social: {
    label: "Социальные",
    color: "var(--accent)",
    icon: "СЦ",
    description: "Поведение определяется социальным контекстом — семья, окружение.",
    key_skills: ["empathy", "rapport_building", "adaptation"],
  },
  temporal: {
    label: "Ситуативные",
    color: "var(--accent)",
    icon: "СТ",
    description: "Поведение определяется текущей ситуацией, а не характером.",
    key_skills: ["empathy", "time_management", "closing"],
  },
  professional: {
    label: "Профессиональные",
    color: "var(--accent)",
    icon: "ПР",
    description: "Поведение определяется профессией и профессиональной деформацией.",
    key_skills: ["adaptation", "knowledge", "legal_knowledge"],
  },
  compound: {
    label: "Гибриды",
    color: "var(--accent)",
    icon: "ГБ",
    description: "Комбинации базовых архетипов. Самые сложные и непредсказуемые.",
    key_skills: ["empathy", "stress_resistance", "adaptation"],
  },
};

// ─── 100 Archetypes ─────────────────────────────────────────────────────────

export const ARCHETYPES: ArchetypeInfo[] = [
  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 1: RESISTANCE (Сопротивление) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "skeptic", name: "Скептик", subtitle: "Фома неверующий",
    description: "Сомневается в легальности, требует доказательств, не верит на слово.",
    detailed_behavior: "Не агрессивен, но всё ставит под сомнение. Требует конкретных цифр, решений суда, примеров из практики. Каждый аргумент встречает \"А если...\". Менеджеру нужно вооружиться фактами.",
    group: "resistance", tier: 1, difficulty: 4, unlock_level: 1,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["confrontation"], counters: ["objection_handling", "knowledge"],
    weakness: "Конкретный кейс из его ситуации с цифрами и номером дела",
  },
  {
    code: "blamer", name: "Обвинитель", subtitle: "Во всём виноваты вы",
    description: "Перекладывает вину на всех: банки, государство, менеджера.",
    detailed_behavior: "Эмоционально давит через обвинения: \"Это вы виноваты!\", \"Ваша компания...\". Не даёт менеджеру говорить, перебивает. Ключ — не оправдываться, а перенаправить на решение.",
    group: "resistance", tier: 2, difficulty: 6, unlock_level: 3,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["anger", "emotional_pressure"], counters: ["stress_resistance", "objection_handling"],
    weakness: "Валидация чувств + переключение на конкретный план действий",
  },
  {
    code: "sarcastic", name: "Саркастичный", subtitle: "Ну-ну, расскажите ещё",
    description: "Язвительный, обесценивает усилия менеджера насмешками.",
    detailed_behavior: "Каждое предложение встречает иронией. \"Конечно, вы же спасители\". Менеджер чувствует что его не воспринимают всерьёз. Ключ — не вестись на провокации и показать экспертизу.",
    group: "resistance", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["confrontation", "deception"], counters: ["stress_resistance", "adaptation"],
    weakness: "Самоирония менеджера + неожиданная конкретика",
  },
  {
    code: "aggressive", name: "Агрессор", subtitle: "Повышенный тон",
    description: "Враждебный, повышает голос, угрожает, обвиняет.",
    detailed_behavior: "Кричит, перебивает, угрожает жалобами. Тестирует менеджера на стрессоустойчивость. Часто за агрессией скрывается страх. Менеджер должен оставаться спокойным и не отвечать агрессией.",
    group: "resistance", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["yelling", "anger", "confrontation"], counters: ["stress_resistance", "empathy"],
    weakness: "Спокойный тон + признание его права на злость",
  },
  {
    code: "hostile", name: "Враждебный", subtitle: "Война объявлена",
    description: "Открыто конфликтует, провоцирует, отказывается слушать.",
    detailed_behavior: "Личные нападки, оскорбления, отказ от любого диалога. Boss-уровень группы Resistance. Менеджер должен найти причину враждебности и обезоружить эмпатией.",
    group: "resistance", tier: 4, difficulty: 9, unlock_level: 9,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["yelling", "anger", "confrontation"], counters: ["stress_resistance", "empathy", "adaptation"],
    weakness: "Обнаружение скрытого страха за агрессией",
  },
  {
    code: "stubborn", name: "Упёртый", subtitle: "Я сказал — нет",
    description: "Просто говорит \"нет\". Стена без аргументов.",
    detailed_behavior: "Не агрессивен, не враждебен — просто \"нет\" и точка. Не приводит контраргументов. Менеджеру нужно найти ключ, который откроет дверь — конкретный кейс из его ситуации.",
    group: "resistance", tier: 1, difficulty: 3, unlock_level: 2,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["silence", "monosyllabic", "confrontation"], counters: ["rapport_building", "adaptation"],
    weakness: "Конкретный кейс из его реальной ситуации",
  },
  {
    code: "conspiracy", name: "Конспиролог", subtitle: "Это всё схема",
    description: "Считает банкротство мошенничеством, начитался форумов.",
    detailed_behavior: "\"Банкротство — схема чтобы отобрать квартиру\". Начитался Telegram-каналов и YouTube-юристов. Своя картина мира. Менеджеру нужно разрушить мифы фактами, не спорить.",
    group: "resistance", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["fear", "information_warfare"], counters: ["knowledge", "legal_knowledge"],
    weakness: "Ссылка на конкретное решение суда по его ситуации",
  },
  {
    code: "righteous", name: "Праведник", subtitle: "Я ничего не нарушал",
    description: "Считает банкротство стигмой, моральная стена.",
    detailed_behavior: "\"Я всю жизнь честно работал, а теперь БАНКРОТСТВО?\" Не может принять что порядочный человек может обанкротиться. Менеджеру нужно переформатировать банкротство как защиту прав.",
    group: "resistance", tier: 3, difficulty: 7, unlock_level: 6,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["pride", "confrontation"], counters: ["empathy", "adaptation", "legal_knowledge"],
    weakness: "127-ФЗ — закон для ЗАЩИТЫ граждан, а не наказания",
  },
  {
    code: "litigious", name: "Сутяжник", subtitle: "Я на вас в суд подам",
    description: "Угрожает жалобами, судами, проверками. Использует закон как оружие.",
    detailed_behavior: "\"Я записываю разговор. 152-ФЗ о персональных данных. Роспотребнадзор.\" Часто неправильно цитирует законы. Менеджер должен быть спокоен и юридически грамотен.",
    group: "resistance", tier: 3, difficulty: 8, unlock_level: 8,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["legal_traps", "confrontation"], counters: ["legal_knowledge", "stress_resistance", "objection_handling"],
    weakness: "Когда менеджер показывает РЕАЛЬНОЕ знание закона — уважение к профессионалу",
  },
  {
    code: "scorched_earth", name: "Выжженная земля", subtitle: "Мне уже нечего терять",
    description: "Полная апатия. Потерял всё. Нет рычага давления.",
    detailed_behavior: "\"Мне уже всё равно. Делайте что хотите.\" Квартиру заберут, зарплату арестуют, жена ушла. Пустота, не агрессия. Менеджеру нужно найти СМЫСЛ — единственный якорь (дети, родители).",
    group: "resistance", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--danger)", icon: "\u{1F6E1}\uFE0F",
    tags: ["nihilism", "silence"], counters: ["empathy", "rapport_building", "closing"],
    weakness: "Забота о ком-то (дети, родители) — единственный якорь",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 2: EMOTIONAL (Эмоциональные) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "grateful", name: "Благодарный", subtitle: "Спасибо что позвонили",
    description: "Готов сотрудничать, ценит помощь, лёгкий на закрытие.",
    detailed_behavior: "Самый лёгкий клиент. Благодарит, слушает, соглашается. Ловушка для менеджера: расслабиться и не квалифицировать должным образом.",
    group: "emotional", tier: 1, difficulty: 2, unlock_level: 1,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["cooperation", "hope"], counters: ["closing", "qualification"],
    weakness: "Практически без сопротивления — но менеджер должен не расслабляться",
  },
  {
    code: "anxious", name: "Тревожный", subtitle: "А вдруг станет хуже?",
    description: "Боится юридических последствий, катастрофизирует.",
    detailed_behavior: "\"А что если банк подаст в суд? А имущество заберут? А на работе узнают?\" Каждый ответ порождает новый страх. Менеджеру нужно успокаивать фактами, не обесценивая страхи.",
    group: "emotional", tier: 1, difficulty: 4, unlock_level: 1,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["fear", "emotional_pressure"], counters: ["empathy", "knowledge"],
    weakness: "Пошаговый план с конкретными датами снимает тревогу",
  },
  {
    code: "ashamed", name: "Стыдящийся", subtitle: "Мне так стыдно...",
    description: "Стесняется своей ситуации, говорит тихо, скрывает детали.",
    detailed_behavior: "Стыд мешает рассказать правду. Занижает суммы долга, скрывает количество кредитов. Менеджеру нужно создать безопасное пространство без осуждения.",
    group: "emotional", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["shame", "silence"], counters: ["empathy", "rapport_building"],
    weakness: "Нормализация: \"Тысячи людей в такой же ситуации\"",
  },
  {
    code: "overwhelmed", name: "Перегруженный", subtitle: "Я уже ничего не понимаю",
    description: "Запутался, не может принять решение, информационный перегруз.",
    detailed_behavior: "Слишком много звонков, слишком много информации. Не может отличить важное от неважного. Менеджеру нужно УПРОСТИТЬ: один шаг за раз.",
    group: "emotional", tier: 2, difficulty: 5, unlock_level: 5,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["fear", "emotional_pressure"], counters: ["empathy", "adaptation"],
    weakness: "Простой пошаговый план: \"Сейчас нужно сделать только ОДНО\"",
  },
  {
    code: "desperate", name: "Отчаявшийся", subtitle: "Нет выхода...",
    description: "На грани, потерял надежду, эмоциональный коллапс.",
    detailed_behavior: "\"Я уже не знаю что делать. Всё бесполезно.\" Нуждается в реальной надежде, не в ложных обещаниях. Менеджер должен быть мостом к решению.",
    group: "emotional", tier: 3, difficulty: 7, unlock_level: 6,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["fear", "emotional_pressure", "crisis"], counters: ["empathy", "rapport_building", "closing"],
    weakness: "Конкретный пример человека в похожей ситуации, который справился",
  },
  {
    code: "crying", name: "Плачущий", subtitle: "Извините... *плачет*",
    description: "Эмоционально подавлен, плачет во время разговора.",
    detailed_behavior: "Плач, паузы, извинения за слёзы. Менеджер должен дать время, не торопить, показать что плакать — нормально. НЕ обесценивать: \"Не плачьте\" = ошибка.",
    group: "emotional", tier: 3, difficulty: 7, unlock_level: 8,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["emotional_pressure", "silence"], counters: ["empathy", "rapport_building", "time_management"],
    weakness: "Пауза + \"Я здесь, не тороплюсь\" + мягкий переход к решению",
  },
  {
    code: "guilty", name: "Виноватый", subtitle: "Это я во всём виноват",
    description: "Наказывает сам себя, считает банкротство незаслуженным облегчением.",
    detailed_behavior: "\"Я сам набрал кредиты. Заслужил.\" Считает что банкротство — слишком лёгкий выход. Менеджеру нужно сместить фокус с вины на решение, ради семьи.",
    group: "emotional", tier: 1, difficulty: 3, unlock_level: 2,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["shame", "cooperation"], counters: ["empathy", "rapport_building"],
    weakness: "\"Вы не виноваты в системе. Но вы можете помочь семье сейчас\"",
  },
  {
    code: "mood_swinger", name: "Маятник", subtitle: "То смеюсь, то плачу",
    description: "Эмоции скачут непредсказуемо. Резкие перепады настроения.",
    detailed_behavior: "Минуту назад смеялся — сейчас кричит — через минуту извиняется. Непредсказуемый. Менеджер должен быть якорем стабильности в шторме.",
    group: "emotional", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["emotional_pressure"], counters: ["stress_resistance", "adaptation"],
    weakness: "Стабильный, спокойный тон менеджера постепенно \"заземляет\"",
  },
  {
    code: "frozen", name: "Замороженный", subtitle: "*длинное молчание*",
    description: "Эмоциональное оцепенение. Односложные ответы, молчит.",
    detailed_behavior: "\"Да.\" \"Нет.\" \"Не знаю.\" 80% ответов < 5 слов. Не кладёт трубку, но и не говорит. Менеджеру нужно \"разморозить\" — открытые вопросы о повседневности.",
    group: "emotional", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["silence", "monosyllabic"], counters: ["rapport_building", "empathy", "time_management"],
    weakness: "Открытые вопросы о повседневности (\"А как дети? Работаете?\")",
  },
  {
    code: "hysteric", name: "Истерик", subtitle: "ВСЁ ПРОПАЛО!!!",
    description: "Паника, крик, слёзы, перескакивание с темы на тему.",
    detailed_behavior: "\"У МЕНЯ ПРИСТАВЫ! ЗАВТРА ЗАБЕРУТ КВАРТИРУ!\" Острый кризис. Менеджер должен СНАЧАЛА стабилизировать, ПОТОМ продавать. Чёткий пошаговый план — \"якорь\".",
    group: "emotional", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--accent)", icon: "\u{1F49C}",
    tags: ["yelling", "emotional_pressure", "crisis"], counters: ["stress_resistance", "empathy", "time_management"],
    weakness: "Чёткий спокойный пошаговый план: \"Давайте по порядку. Первое...\"",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 3: CONTROL (Контроль) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "pragmatic", name: "Прагматик", subtitle: "Покажите цифры",
    description: "Фокус на ROI и конкретных числах. Без эмоций.",
    detailed_behavior: "\"Сколько стоит? Какие сроки? Какой процент успеха?\" Только факты. Не терпит \"воды\" и общих фраз. Менеджеру нужно быть готовым с цифрами.",
    group: "control", tier: 1, difficulty: 4, unlock_level: 1,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["cooperation"], counters: ["knowledge", "closing"],
    weakness: "Конкретные цифры: стоимость, сроки, вероятность успеха",
  },
  {
    code: "shopper", name: "Шоппер", subtitle: "Я ещё думаю",
    description: "Сравнивает предложения, не торопится, ищет альтернативы.",
    detailed_behavior: "\"А в другой компании дешевле\". \"Мне нужно подумать\". Вечно сравнивает. Менеджеру нужно показать уникальную ценность, не вступая в ценовую войну.",
    group: "control", tier: 1, difficulty: 4, unlock_level: 3,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["avoidance", "deception"], counters: ["objection_handling", "closing"],
    weakness: "Уникальное преимущество компании + ограничение по времени",
  },
  {
    code: "negotiator", name: "Торговец", subtitle: "А если скидку?",
    description: "Выбивает скидки и особые условия. Торгуется за каждую копейку.",
    detailed_behavior: "Превращает каждый пункт в предмет торга. \"А если я приведу друга?\", \"А рассрочка?\". Менеджер должен знать границы уступок и уметь создавать ценность.",
    group: "control", tier: 2, difficulty: 6, unlock_level: 4,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["manipulation", "confrontation"], counters: ["objection_handling", "closing"],
    weakness: "Фиксация ценности ДО обсуждения цены",
  },
  {
    code: "know_it_all", name: "Всезнайка", subtitle: "Я лучше знаю",
    description: "Считает себя экспертом, поучает менеджера.",
    detailed_behavior: "\"Я уже всё прочитал в интернете\". Перебивает, поправляет, демонстрирует \"знания\" (часто неполные). Менеджер должен показать экспертизу, не унижая.",
    group: "control", tier: 3, difficulty: 7, unlock_level: 6,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["pride", "information_warfare", "confrontation"], counters: ["knowledge", "legal_knowledge", "adaptation"],
    weakness: "Признание его знаний + мягкое дополнение профессиональной экспертизой",
  },
  {
    code: "manipulator", name: "Манипулятор", subtitle: "Давайте по-другому",
    description: "Контролирует разговор, тестирует границы, перенаправляет.",
    detailed_behavior: "Газлайтинг, подмена тезисов, давление через лесть и вину. Опытный в управлении людьми. Менеджер должен удерживать границы и не вестись.",
    group: "control", tier: 3, difficulty: 8, unlock_level: 7,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["manipulation", "deception"], counters: ["stress_resistance", "objection_handling"],
    weakness: "Прямое называние манипуляции без обвинения",
  },
  {
    code: "lawyer_client", name: "Юрист-клиент", subtitle: "По закону...",
    description: "Знает законы, проверяет каждое слово, ставит юридические ловушки.",
    detailed_behavior: "Цитирует статьи, задаёт точные вопросы, проверяет компетентность. Одна ошибка менеджера = потеря доверия. Требует идеального знания 127-ФЗ.",
    group: "control", tier: 4, difficulty: 9, unlock_level: 9,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["legal_traps", "confrontation"], counters: ["legal_knowledge", "knowledge", "stress_resistance"],
    weakness: "Безупречное знание закона вызывает уважение профессионала",
  },
  {
    code: "auditor", name: "Аудитор", subtitle: "Покажите лицензию",
    description: "Методично проверяет компанию. Не враждебен — верифицирует.",
    detailed_behavior: "\"Покажите лицензию. Сколько лет на рынке? Есть решения суда?\" Спокойно и документально проверяет. Менеджер должен быть готов с доказательствами.",
    group: "control", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["cooperation"], counters: ["knowledge", "legal_knowledge"],
    weakness: "Готовность к документам и конкретным цифрам → быстрое доверие",
  },
  {
    code: "strategist", name: "Стратег", subtitle: "У меня свой план",
    description: "Пришёл с собственным планом (часто ошибочным).",
    detailed_behavior: "\"Я уже посчитал: если платить минимальные платежи год, потом подать...\" Спорит не из агрессии, а из убеждённости. Менеджер должен уважительно показать слабые места плана.",
    group: "control", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["pride", "confrontation"], counters: ["knowledge", "objection_handling", "legal_knowledge"],
    weakness: "Логическая аргументация с примерами ошибок в его плане",
  },
  {
    code: "power_player", name: "Властелин", subtitle: "Вы знаете кто я?",
    description: "Привык командовать. Не терпит шаблонов, требует индивидуального подхода.",
    detailed_behavior: "\"Я директор компании. 50 сотрудников. Давайте по существу.\" Статус, авторитет, доминирование. Менеджер должен перейти на \"язык руководителя\".",
    group: "control", tier: 3, difficulty: 8, unlock_level: 8,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["pride", "confrontation"], counters: ["adaptation", "closing", "time_management"],
    weakness: "Деловой подход, ROI в конкретных цифрах, уважение к его времени",
  },
  {
    code: "puppet_master", name: "Кукловод", subtitle: "А давайте вы скажете...",
    description: "Ведёт менеджера к нужным ему ответам. Каскад вопросов-ловушек.",
    detailed_behavior: "Самый опасный. Задаёт \"невинные\" вопросы, каждый из которых ловушка. Каскад: \"Гарантируете?\" → \"А если суд откажет?\" → \"Тогда зря заплатил?\".",
    group: "control", tier: 4, difficulty: 10, unlock_level: 11,
    color: "var(--warning)", icon: "\u{1F451}",
    tags: ["manipulation", "deception", "legal_traps"], counters: ["stress_resistance", "objection_handling", "closing"],
    weakness: "Прямое называние манипуляции: \"Я вижу, что вы ведёте к определённому выводу\"",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 4: AVOIDANCE (Избегание) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "passive", name: "Пассивный", subtitle: "Ну ладно...",
    description: "Безынициативный, соглашается со всем, ждёт что решат за него.",
    detailed_behavior: "\"Ну ладно. Как скажете.\" Не спорит, но и не действует. Менеджер должен вести, но не быть директивным — иначе клиент \"потеряется\" после звонка.",
    group: "avoidance", tier: 1, difficulty: 3, unlock_level: 1,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["cooperation", "avoidance"], counters: ["closing", "rapport_building"],
    weakness: "Чёткий пошаговый план с конкретными действиями",
  },
  {
    code: "delegator", name: "Делегатор", subtitle: "Решите за меня",
    description: "Избегает решений, хочет чтобы менеджер всё сделал за него.",
    detailed_behavior: "\"А вы не можете просто всё оформить? Я подпишу.\" Перекладывает ответственность. Менеджер должен мягко вовлекать в принятие решений.",
    group: "avoidance", tier: 1, difficulty: 3, unlock_level: 2,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["avoidance"], counters: ["closing", "adaptation"],
    weakness: "Разбить задачу на мини-решения: \"Нам нужно только одно ваше решение\"",
  },
  {
    code: "avoidant", name: "Уклонист", subtitle: "Давайте потом",
    description: "Уходит от темы, переносит разговор, находит отговорки.",
    detailed_behavior: "\"Сейчас неудобно. Перезвоните завтра. Нет, лучше на следующей неделе.\" Бесконечный цикл переносов. Менеджер должен фиксировать конкретное время.",
    group: "avoidance", tier: 2, difficulty: 5, unlock_level: 3,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["avoidance", "time_pressure"], counters: ["closing", "time_management"],
    weakness: "Конкретный вопрос: \"Когда именно вам удобно? Я запишу\"",
  },
  {
    code: "paranoid", name: "Параноик", subtitle: "Это всё развод",
    description: "Не доверяет никому, ищет подвох в каждом слове.",
    detailed_behavior: "\"Вы записываете? Это ловушка? Зачем вам мои данные?\" Видит заговор везде. Менеджер должен быть максимально прозрачным и не давить.",
    group: "avoidance", tier: 3, difficulty: 7, unlock_level: 6,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["fear", "avoidance"], counters: ["rapport_building", "empathy", "legal_knowledge"],
    weakness: "Максимальная прозрачность: \"Вот наш договор, читайте не торопясь\"",
  },
  {
    code: "procrastinator", name: "Прокрастинатор", subtitle: "Завтра позвоню",
    description: "Бесконечно откладывает. Никогда не перезвонит.",
    detailed_behavior: "\"Звучит интересно. Давайте я подумаю и перезвоню.\" Классический тёплый отказ. Не говорит \"нет\" — говорит \"потом\". Менеджеру нужно создать мотивацию действовать СЕЙЧАС.",
    group: "avoidance", tier: 1, difficulty: 3, unlock_level: 1,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["avoidance", "deception"], counters: ["closing", "time_management"],
    weakness: "Конкретный дедлайн с последствиями бездействия",
  },
  {
    code: "ghosting", name: "Призрак", subtitle: "*пропал*",
    description: "Исчезает без предупреждения. Не берёт трубку, не отвечает.",
    detailed_behavior: "Был на связи — и пропал. Менеджер звонит в пустоту. Если дозвонился — \"Ой, я забыл\". Ключ — удержать до конкретного обязательства в ЭТОМ звонке.",
    group: "avoidance", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["avoidance", "silence"], counters: ["closing", "rapport_building"],
    weakness: "Зафиксировать конкретное обязательство с датой и временем",
  },
  {
    code: "deflector", name: "Отклонитель", subtitle: "А у вас тоже кредиты?",
    description: "Уводит разговор на личные вопросы к менеджеру.",
    detailed_behavior: "\"А вы сами банкротились? А сколько вам лет? А вам нравится работа?\" Перенаправляет фокус с себя на менеджера. Менеджер должен мягко возвращать разговор.",
    group: "avoidance", tier: 2, difficulty: 5, unlock_level: 5,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["avoidance", "manipulation"], counters: ["adaptation", "time_management"],
    weakness: "\"Понимаю любопытство, но давайте вернёмся к вашей ситуации\"",
  },
  {
    code: "agreeable_ghost", name: "Да-нет", subtitle: "Да-да, я подумаю",
    description: "Со всем соглашается, но никогда не действует. Иллюзия прогресса.",
    detailed_behavior: "\"Да, конечно. Да, я понимаю. Да, давайте встретимся.\" Но не приходит, не звонит, не отправляет документы. Самый коварный — менеджер думает клиент \"в работе\".",
    group: "avoidance", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["deception", "avoidance"], counters: ["closing", "qualification"],
    weakness: "Фиксация конкретных обязательств: \"Когда именно вы отправите документы?\"",
  },
  {
    code: "fortress", name: "Крепость", subtitle: "Мне ничего не надо",
    description: "Полная закрытость. Односложные ответы, непробиваемый.",
    detailed_behavior: "Похож на frozen, но не из-за эмоций — из-за решения. Осознанно закрылся. \"Нет\", \"Не надо\", \"Не интересно\". Менеджеру нужно найти единственную трещину.",
    group: "avoidance", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["silence", "monosyllabic", "confrontation"], counters: ["rapport_building", "adaptation"],
    weakness: "Неожиданный факт о его конкретной ситуации, который он не ожидал",
  },
  {
    code: "smoke_screen", name: "Дымовая завеса", subtitle: "Давайте я вам расскажу...",
    description: "Уводит разговор длинными историями, тратит время менеджера.",
    detailed_behavior: "\"А вот у моего брата был случай...\" Бесконечные истории, не дающие менеджеру вести разговор. Ключ — ВЕЖЛИВО перехватить контроль и не позволять говорить > 70% времени.",
    group: "avoidance", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--accent)", icon: "\u{1F32B}\uFE0F",
    tags: ["long_stories", "avoidance", "time_pressure"], counters: ["time_management", "closing", "adaptation"],
    weakness: "Вежливое перехватывание: \"Понимаю, а давайте конкретно по вашей ситуации\"",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 5: SPECIAL (Особые) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "referred", name: "По рекомендации", subtitle: "Мне посоветовал друг",
    description: "Тёплый лид, доверие передано от знакомого. Быстрый close.",
    detailed_behavior: "\"Мне Вася посоветовал, он сказал вы помогли.\" Уже есть базовое доверие. Менеджер должен не упустить тёплый контакт и не расслабляться.",
    group: "special", tier: 1, difficulty: 3, unlock_level: 2,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["cooperation", "hope"], counters: ["closing", "qualification"],
    weakness: "Ссылка на успешный опыт рекомендателя",
  },
  {
    code: "returner", name: "Возвращенец", subtitle: "Я передумал",
    description: "Уже отказывался, теперь звонит снова. Второй шанс.",
    detailed_behavior: "\"Я вам звонил месяц назад и отказался. Но ситуация ухудшилась.\" Нужно понять причину отказа и не повторять ошибку первого звонка.",
    group: "special", tier: 2, difficulty: 6, unlock_level: 4,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["fear"], counters: ["adaptation", "objection_handling"],
    weakness: "Анализ причины первого отказа и демонстрация изменений",
  },
  {
    code: "rushed", name: "Спешащий", subtitle: "У меня 5 минут",
    description: "Нет времени, требует результата за минимальное время.",
    detailed_behavior: "\"Быстрее. У меня 5 минут. Суть?\" Менеджер должен быть максимально лаконичен и ценить время клиента. Каждая секунда на счету.",
    group: "special", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["time_pressure"], counters: ["closing", "time_management"],
    weakness: "Лаконичная подача: проблема → решение → действие за 3 минуты",
  },
  {
    code: "couple", name: "Пара", subtitle: "Мы вместе решаем",
    description: "Два человека с разными мнениями на одном звонке.",
    detailed_behavior: "Двойная механика: один хочет, другой сомневается. Менеджер должен работать с обоими, не принимая чью-то сторону. Медиатор, не продавец.",
    group: "special", tier: 3, difficulty: 8, unlock_level: 7,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["family"], counters: ["adaptation", "empathy", "closing"],
    weakness: "Найти общий интерес пары (дети, дом, будущее)",
  },
  {
    code: "elderly", name: "Пожилой", subtitle: "Доченька, объясните помедленнее",
    description: "Плохо разбирается в терминах, нуждается в терпеливом объяснении.",
    detailed_behavior: "Переспрашивает 3-4 раза. Нуждается в простых словах. Менеджер — учитель, не продавец. Использование сложных терминов без объяснения — ошибка.",
    group: "special", tier: 1, difficulty: 3, unlock_level: 2,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["cooperation", "family"], counters: ["empathy", "adaptation"],
    weakness: "Простые слова + повторение + терпение",
  },
  {
    code: "young_debtor", name: "Молодой должник", subtitle: "Мне 24, у меня кредитка...",
    description: "Первый долг, наивен, технически подкован.",
    detailed_behavior: "\"Я просто не рассчитал с кредиткой.\" Первый серьёзный долг. Стыдится, но открыт к технологиям. Быстро схватывает если объяснить.",
    group: "special", tier: 1, difficulty: 4, unlock_level: 3,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["shame", "cooperation"], counters: ["empathy", "closing"],
    weakness: "Нормализация + простая схема \"что делать\" с digital-инструментами",
  },
  {
    code: "foreign_speaker", name: "Иностранец", subtitle: "Я... плохо понимать русский",
    description: "Языковой барьер. Нужны простые слова и терпение.",
    detailed_behavior: "Плохо говорит по-русски, не понимает юридические термины. Менеджер должен говорить просто, медленно, проверять понимание.",
    group: "special", tier: 2, difficulty: 6, unlock_level: 6,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["cooperation"], counters: ["empathy", "adaptation"],
    weakness: "Простые формулировки + проверка понимания + визуальные материалы",
  },
  {
    code: "intermediary", name: "Посредник", subtitle: "Я звоню за маму",
    description: "Звонит за родственника. Информация неполная, решения не принимает.",
    detailed_behavior: "\"Мама не может говорить, она в больнице.\" Менеджер работает через третье лицо. Обязан уточнить полномочия посредника.",
    group: "special", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["family"], counters: ["legal_knowledge", "adaptation"],
    weakness: "Чёткий план: кто принимает решение и как организовать прямой контакт",
  },
  {
    code: "repeat_caller", name: "Хронический звонящий", subtitle: "Я уже 10-й раз звоню",
    description: "Много раз обращался, никто не помог. Фрустрация и недоверие.",
    detailed_behavior: "\"Мне все обещали и никто не сделал.\" Накопленная фрустрация от системы. Менеджер должен отличиться от предыдущих: конкретикой и действием.",
    group: "special", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["anger", "fear"], counters: ["empathy", "stress_resistance", "closing"],
    weakness: "\"Я понимаю ваш опыт. Давайте я покажу что мы СДЕЛАЕМ, а не пообещаем\"",
  },
  {
    code: "celebrity", name: "VIP-клиент", subtitle: "Если об этом узнают...",
    description: "Публичная персона. Конфиденциальность — главный приоритет.",
    detailed_behavior: "Бизнесмен/блогер/чиновник. Главный страх — утечка. Каждое слово взвешено. Может записывать. Одно нарушение конфиденциальности = мгновенный hangup.",
    group: "special", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--magenta)", icon: "\u2B50",
    tags: ["fear", "legal_traps"], counters: ["legal_knowledge", "adaptation", "stress_resistance"],
    weakness: "Гарантии конфиденциальности подкреплённые конкретными мерами",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 6: COGNITIVE (Когнитивные) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "overthinker", name: "Аналитик-паралитик", subtitle: "А если рассмотреть ещё...",
    description: "Бесконечно анализирует. Каждый ответ порождает 3 вопроса.",
    detailed_behavior: "\"А что если банк подаст апелляцию? А если закон изменится?\" Анализ-паралич. Менеджер должен ОГРАНИЧИТЬ поток и направить к решению.",
    group: "cognitive", tier: 1, difficulty: 4, unlock_level: 2,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["avoidance", "information_warfare"], counters: ["closing", "adaptation"],
    weakness: "Фокусирование: \"Сейчас нужно решить только ОДИН вопрос\"",
  },
  {
    code: "concrete", name: "Конкретик", subtitle: "Не надо воды — давайте факты",
    description: "Не терпит \"воду\". Только факты, цифры, действия.",
    detailed_behavior: "\"Давайте без вступлений. Суть?\" Экономит каждую секунду. Любая \"вода\" — откат. Менеджер должен быть лаконичен и структурирован.",
    group: "cognitive", tier: 1, difficulty: 3, unlock_level: 1,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["cooperation", "time_pressure"], counters: ["knowledge", "closing"],
    weakness: "Структурированная подача: \"Три факта о вашей ситуации\"",
  },
  {
    code: "storyteller", name: "Рассказчик", subtitle: "Вот слушайте как было...",
    description: "Любит длинные истории. Уводит разговор, но не злонамеренно.",
    detailed_behavior: "\"А вот в 2015 году я...\" Не манипулирует — просто так думает и общается. Менеджер должен слушать, но мягко направлять к сути.",
    group: "cognitive", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["long_stories"], counters: ["time_management", "rapport_building"],
    weakness: "Использование его историй как мост к решению",
  },
  {
    code: "misinformed", name: "Дезинформированный", subtitle: "Мне сказали что...",
    description: "Ошибочная информация от друзей/интернета. Нужно мягко корректировать.",
    detailed_behavior: "\"Мне сосед сказал что при банкротстве заберут всё имущество.\" Мифы и заблуждения. Менеджер должен развенчать мягко, без \"вы неправы\".",
    group: "cognitive", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["information_warfare"], counters: ["knowledge", "legal_knowledge"],
    weakness: "\"Частое заблуждение. На самом деле закон говорит...\"",
  },
  {
    code: "selective_listener", name: "Фильтратор", subtitle: "Нет, вы сказали другое",
    description: "Слышит только что хочет. Перекручивает слова менеджера.",
    detailed_behavior: "\"Вы же сказали что долг ТОЧНО спишут!\" (менеджер говорил \"в большинстве случаев\"). Запоминает неточности и использует потом. Менеджер должен быть ПРЕДЕЛЬНО точным.",
    group: "cognitive", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["manipulation", "legal_traps"], counters: ["legal_knowledge", "stress_resistance"],
    weakness: "Чёткие формулировки с проверкой понимания: \"Повторите как вы поняли?\"",
  },
  {
    code: "black_white", name: "Чёрно-белый", subtitle: "Или спишут ВСЁ, или ничего",
    description: "Бинарное мышление. Нет полутонов, нет нюансов.",
    detailed_behavior: "\"Или гарантируете 100%, или я не буду.\" Мир делится на чёрное и белое. Менеджер должен мягко показать спектр возможностей.",
    group: "cognitive", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["confrontation"], counters: ["adaptation", "knowledge"],
    weakness: "Разложить на этапы: \"Смотрите, есть несколько вариантов развития...\"",
  },
  {
    code: "memory_issues", name: "Забывчивый", subtitle: "Мы разве говорили?",
    description: "Забывает информацию из предыдущих разговоров. Нужны повторы.",
    detailed_behavior: "\"А разве мы это обсуждали?\" Не притворяется — реально забывает. Менеджер должен терпеливо повторять и фиксировать письменно.",
    group: "cognitive", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["cooperation"], counters: ["empathy", "time_management", "adaptation"],
    weakness: "Письменная фиксация: \"Я отправлю вам SMS с ключевыми моментами\"",
  },
  {
    code: "technical", name: "Технарь", subtitle: "Объясните алгоритм",
    description: "Системное мышление. Хочет понять процесс как flowchart.",
    detailed_behavior: "\"А какой алгоритм? Что за чем? Есть схема?\" Думает процессами. Менеджер должен дать структуру: шаг 1, шаг 2, шаг 3.",
    group: "cognitive", tier: 2, difficulty: 5, unlock_level: 5,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["cooperation"], counters: ["knowledge", "adaptation"],
    weakness: "Пошаговая схема процесса с таймлайном",
  },
  {
    code: "magical_thinker", name: "Волшебник", subtitle: "А может как-то само?",
    description: "Верит в чудо. Надеется что проблема решится сама.",
    detailed_behavior: "\"А может если подождать, банк забудет?\" \"А может амнистию объявят?\" Нереалистичные ожидания. Менеджер должен мягко вернуть в реальность.",
    group: "cognitive", tier: 3, difficulty: 7, unlock_level: 8,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["avoidance", "deception"], counters: ["knowledge", "legal_knowledge", "closing"],
    weakness: "Конкретные последствия бездействия с датами и суммами",
  },
  {
    code: "lawyer_level_2", name: "Квази-юрист", subtitle: "Я читал на форуме...",
    description: "Начитался форумов, уверен в ошибочных знаниях. Опаснее настоящего юриста.",
    detailed_behavior: "Цитирует устаревшие статьи закона с высокой уверенностью. Считает себя экспертом. Менеджер ОБЯЗАН корректировать ошибки ТАКТИЧНО — \"вы неправы\" = hostile.",
    group: "cognitive", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--info)", icon: "\u{1F9E0}",
    tags: ["pride", "legal_traps", "information_warfare"], counters: ["legal_knowledge", "adaptation", "stress_resistance"],
    weakness: "\"Да, статья 213.X об этом, но с 2023 практика изменилась...\"",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 7: SOCIAL (Социальные) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "family_man", name: "Семьянин", subtitle: "А что будет с детьми?",
    description: "Всё через призму семьи. Главный страх — последствия для близких.",
    detailed_behavior: "\"А детей не заберут? А квартиру? А муж/жена пострадает?\" Все решения оценивает через влияние на семью. Менеджер должен успокоить по каждому пункту.",
    group: "social", tier: 1, difficulty: 3, unlock_level: 2,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["fear", "family"], counters: ["empathy", "knowledge"],
    weakness: "\"Банкротство ЗАЩИЩАЕТ семью. Имущество — под контролем\"",
  },
  {
    code: "influenced", name: "Под влиянием", subtitle: "Муж/жена сказал(а) не надо",
    description: "Решение принимает не он — а супруг/родственник.",
    detailed_behavior: "\"Я бы хотел, но жена сказала не связываться.\" Зависим от мнения близких. Менеджер должен работать с НАСТОЯЩИМ принимателем решения.",
    group: "social", tier: 1, difficulty: 4, unlock_level: 3,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["avoidance", "family"], counters: ["adaptation", "closing"],
    weakness: "\"Давайте я объясню и вашей жене/мужу. Когда удобно?\"",
  },
  {
    code: "reputation_guard", name: "Хранитель репутации", subtitle: "А соседи узнают?",
    description: "Боится огласки. Стыд перед окружением важнее финансов.",
    detailed_behavior: "\"А на работе узнают? А соседи? А в кредитной истории будет?\" Репутация важнее денег. Менеджер должен объяснить конфиденциальность процедуры.",
    group: "social", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["shame", "fear"], counters: ["knowledge", "legal_knowledge"],
    weakness: "Детальное объяснение конфиденциальности процедуры банкротства",
  },
  {
    code: "community_leader", name: "Лидер мнений", subtitle: "Я расскажу всем знакомым",
    description: "Влиятельный в своём окружении. Может привести или увести клиентов.",
    detailed_behavior: "\"У меня 500 подписчиков. Я расскажу как всё прошло.\" Высокие ставки: хороший сервис = рекомендации. Плохой = антиреклама. VIP-подход.",
    group: "social", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["pride"], counters: ["adaptation", "closing"],
    weakness: "Индивидуальный подход + признание его влияния",
  },
  {
    code: "breadwinner", name: "Кормилец", subtitle: "На мне вся семья",
    description: "Главный кормилец семьи. Стресс от ответственности за всех.",
    detailed_behavior: "\"Если я не справлюсь, семья останется без денег.\" Страх не за себя — за семью. Менеджер должен показать что банкротство ЗАЩИТИТ доход.",
    group: "social", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["fear", "family", "crisis"], counters: ["empathy", "knowledge"],
    weakness: "\"Арест зарплаты — вот что угрожает семье. Банкротство его СНИМАЕТ\"",
  },
  {
    code: "divorced", name: "Разведённый", subtitle: "Бывший(ая) набрал(а) долги",
    description: "Совместные долги после развода. Злость + юридические сложности.",
    detailed_behavior: "\"Бывший муж набрал кредитов, а платить мне.\" Злость на бывшего партнёра + запутанная юридическая ситуация. Менеджер — и юрист, и психолог.",
    group: "social", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["anger", "family", "legal_traps"], counters: ["empathy", "legal_knowledge"],
    weakness: "Разделение: \"Ваши и его/её долги — это разные ситуации\"",
  },
  {
    code: "guarantor", name: "Поручитель", subtitle: "Я не брал кредит!",
    description: "Поручился за друга/родственника. Острое чувство несправедливости.",
    detailed_behavior: "\"Друг попросил поручиться, теперь не платит, а с МЕНЯ требуют!\" Злость не на менеджера, а на ситуацию. Менеджер должен валидировать чувства И показать выход.",
    group: "social", tier: 3, difficulty: 7, unlock_level: 6,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["anger", "legal_traps"], counters: ["empathy", "legal_knowledge", "stress_resistance"],
    weakness: "Валидация несправедливости + объяснение солидарной ответственности по 127-ФЗ",
  },
  {
    code: "widow", name: "Вдова/Вдовец", subtitle: "Муж умер, остались долги",
    description: "Горе + финансовый кризис. Самый деликатный архетип.",
    detailed_behavior: "Горе и растерянность. Любое давление — мгновенный hangup. Trigger \"pressure\" вес = -2.0. Менеджер должен быть ОЧЕНЬ деликатен. Чистая эмпатия.",
    group: "social", tier: 3, difficulty: 8, unlock_level: 8,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["emotional_pressure", "family", "crisis"], counters: ["empathy", "rapport_building"],
    weakness: "Чистая эмпатия без продажи. Время и деликатность.",
  },
  {
    code: "caregiver", name: "Опекун", subtitle: "У меня на руках больной родитель",
    description: "Ухаживает за больным родственником. Нет времени и сил.",
    detailed_behavior: "\"Мне некогда, мама лежачая.\" Истощение + финансовые проблемы. Менеджер должен максимально упростить процесс и быть терпеливым.",
    group: "social", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["family", "time_pressure", "crisis"], counters: ["empathy", "adaptation", "time_management"],
    weakness: "\"Мы возьмём максимум на себя. Вам нужно только...\" (минимум действий)",
  },
  {
    code: "multi_debtor_family", name: "Семья должников", subtitle: "У нас двое банкротов",
    description: "Несколько банкротств в одной семье. Юридически сложно.",
    detailed_behavior: "\"И у меня долги, и у жены. Можно вместе?\" Координация нескольких процедур. Менеджер должен знать нюансы совместного банкротства.",
    group: "social", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--success)", icon: "\u{1F465}",
    tags: ["family", "legal_traps", "crisis"], counters: ["legal_knowledge", "knowledge", "adaptation"],
    weakness: "Чёткий план: \"Вот как это работает для семьи\"",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 8: TEMPORAL (Ситуативные) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "just_fired", name: "Только уволен", subtitle: "Меня вчера сократили",
    description: "Свежая потеря работы. Шок и неопределённость.",
    detailed_behavior: "\"Вчера сократили. Кредит за квартиру, а платить нечем.\" Свежая рана. Нуждается в срочном плане действий и эмоциональной поддержке.",
    group: "temporal", tier: 1, difficulty: 4, unlock_level: 3,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["crisis", "fear"], counters: ["empathy", "closing"],
    weakness: "Конкретный план: \"Вот что нужно сделать в первую очередь\"",
  },
  {
    code: "collector_call", name: "После коллекторов", subtitle: "Мне звонили с угрозами",
    description: "Напуган незаконными действиями коллекторов.",
    detailed_behavior: "\"Сказали заберут квартиру! Арестуют! Детей заберут!\" Паника от угроз коллекторов. Менеджер должен успокоить и объяснить права (230-ФЗ).",
    group: "temporal", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["fear", "crisis"], counters: ["empathy", "legal_knowledge"],
    weakness: "\"Коллекторы вас обманули. По закону 230-ФЗ они не имеют права...\"",
  },
  {
    code: "court_notice", name: "Получил повестку", subtitle: "Мне пришло из суда",
    description: "Получил судебную повестку. Паника и срочность.",
    detailed_behavior: "\"Пришло из суда! Что делать? Когда являться?\" Реальный дедлайн создаёт мотивацию, но и панику. Менеджер должен объяснить алгоритм действий.",
    group: "temporal", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["fear", "crisis", "time_pressure"], counters: ["knowledge", "legal_knowledge", "closing"],
    weakness: "Чёткий алгоритм: что делать с повесткой пошагово",
  },
  {
    code: "salary_arrest", name: "Арест зарплаты", subtitle: "С карты списали всё!",
    description: "Внезапное списание денег. Злость + паника + срочность.",
    detailed_behavior: "\"Утром зашёл в банк — а там ноль! Всё списали!\" Шок от потери денег. Злость на систему. Менеджер должен объяснить как защитить доходы.",
    group: "temporal", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["anger", "crisis", "time_pressure"], counters: ["empathy", "legal_knowledge", "stress_resistance"],
    weakness: "\"Арест зарплаты — как раз основание для банкротства. Вот план...\"",
  },
  {
    code: "pre_court", name: "Перед судом", subtitle: "Через неделю заседание",
    description: "Скоро суд. Нужна подготовка, время давит.",
    detailed_behavior: "\"Заседание через неделю, что мне делать?\" Реальный таймлайн. Менеджер должен дать конкретный план подготовки.",
    group: "temporal", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["time_pressure", "crisis"], counters: ["legal_knowledge", "time_management", "closing"],
    weakness: "Пошаговый план подготовки к заседанию",
  },
  {
    code: "post_refusal", name: "После отказа суда", subtitle: "Суд отказал в банкротстве",
    description: "Суд отказал. Отчаяние + нужен анализ причин.",
    detailed_behavior: "\"Суд отказал! Что теперь?\" Нуждается в анализе причин отказа и плане апелляции. Эмоциональная опустошённость.",
    group: "temporal", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["fear", "crisis"], counters: ["legal_knowledge", "empathy"],
    weakness: "Анализ причин отказа + план апелляции с конкретными шагами",
  },
  {
    code: "inheritance_trap", name: "Наследство с долгами", subtitle: "Бабушка оставила квартиру и долги",
    description: "Наследство с обременением. Смешанные чувства.",
    detailed_behavior: "\"Бабушка оставила квартиру, но и 2 миллиона долгов.\" Принимать или отказывать? Юридические нюансы + эмоции потери.",
    group: "temporal", tier: 3, difficulty: 7, unlock_level: 8,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["family", "legal_traps", "inheritance"], counters: ["legal_knowledge", "empathy"],
    weakness: "Чёткий расчёт: стоимость наследства vs долги + варианты",
  },
  {
    code: "business_collapse", name: "Бизнес рухнул", subtitle: "Компания закрылась, личные долги",
    description: "Предприниматель с личными поручительствами по бизнес-кредитам.",
    detailed_behavior: "\"Компания обанкротилась, но кредиты-то на мне лично!\" Сложная юридическая ситуация: ИП, ООО, личные поручительства. Большие суммы.",
    group: "temporal", tier: 3, difficulty: 8, unlock_level: 8,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["crisis", "business", "legal_traps"], counters: ["legal_knowledge", "knowledge", "empathy"],
    weakness: "Разделение личных и бизнес-долгов + план действий по каждому",
  },
  {
    code: "medical_crisis", name: "Медицинский кризис", subtitle: "Я/ребёнок болен, нужны деньги",
    description: "Болезнь + долги. Этически самый сложный.",
    detailed_behavior: "\"Ребёнок болен, деньги ушли на лечение, а долги растут.\" Менеджер должен быть ОЧЕНЬ деликатен. Давление = катастрофа.",
    group: "temporal", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["emotional_pressure", "crisis", "family"], counters: ["empathy", "legal_knowledge", "adaptation"],
    weakness: "Максимальная деликатность + информация о социальных программах",
  },
  {
    code: "criminal_risk", name: "На грани уголовки", subtitle: "Мне грозит 177 УК",
    description: "Риск уголовного преследования. Страх + юридическая сложность.",
    detailed_behavior: "\"Банк грозит 159 или 177 УК. Я мошенник?\" Реальная опасность. Менеджер ОБЯЗАН корректно оценить и НЕ давать невыполнимых обещаний.",
    group: "temporal", tier: 4, difficulty: 9, unlock_level: 11,
    color: "var(--warning)", icon: "\u23F3",
    tags: ["fear", "legal_traps", "criminal", "crisis"], counters: ["legal_knowledge", "stress_resistance", "empathy"],
    weakness: "Трезвая оценка рисков + план минимизации без ложных обещаний",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 9: PROFESSIONAL (Профессиональные) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "teacher", name: "Учитель", subtitle: "Объясните как ученику",
    description: "Методичный, задаёт много вопросов, хочет понять до конца.",
    detailed_behavior: "\"А почему именно так? А какие альтернативы?\" Привык учить — теперь хочет БЫТЬ учеником. Терпеливый, но дотошный.",
    group: "professional", tier: 1, difficulty: 3, unlock_level: 3,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["cooperation"], counters: ["knowledge", "adaptation"],
    weakness: "Структурированное объяснение: как урок с планом",
  },
  {
    code: "doctor", name: "Врач", subtitle: "Давайте по симптомам",
    description: "Аналитический подход. Хочет \"диагноз\" и \"лечение\".",
    detailed_behavior: "\"Какие симптомы? Какой диагноз? Какое лечение?\" Мыслит медицинскими метафорами. Менеджер может использовать его язык.",
    group: "professional", tier: 1, difficulty: 4, unlock_level: 3,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["cooperation"], counters: ["knowledge", "adaptation"],
    weakness: "\"Диагноз: долговая нагрузка. Лечение: процедура банкротства\"",
  },
  {
    code: "military", name: "Военный", subtitle: "Коротко и по делу",
    description: "Прямой, командный стиль. Иерархия, дисциплина.",
    detailed_behavior: "\"Давайте без лирики. Задача? План? Сроки?\" Военная прямота. Уважает чёткость и дисциплину. Не терпит \"воду\".",
    group: "professional", tier: 2, difficulty: 5, unlock_level: 5,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["time_pressure", "confrontation"], counters: ["closing", "knowledge"],
    weakness: "Командный стиль: \"Задача → План → Исполнение → Результат\"",
  },
  {
    code: "accountant", name: "Бухгалтер", subtitle: "Покажите расчёт",
    description: "Всё через цифры и документы. Требует расчёт до копейки.",
    detailed_behavior: "\"Покажите расчёт. Какая стоимость? Какие налоговые последствия?\" Дотошен с числами. Менеджер должен быть готов с калькулятором.",
    group: "professional", tier: 2, difficulty: 5, unlock_level: 4,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["cooperation"], counters: ["knowledge", "legal_knowledge"],
    weakness: "Детальный расчёт: стоимость, сроки, экономия, ROI",
  },
  {
    code: "salesperson", name: "Продавец", subtitle: "Я знаю ваши приёмы",
    description: "Мета-клиент: видит все техники продаж и называет их вслух.",
    detailed_behavior: "\"Ой, это из скрипта. Я сам продавец.\" Распознаёт шаблонные фразы, активное слушание, social proof. Хочет \"честный\" разговор.",
    group: "professional", tier: 2, difficulty: 6, unlock_level: 5,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["information_warfare", "pride"], counters: ["adaptation", "stress_resistance"],
    weakness: "Самоирония + разговор \"на равных\" без скрипта",
  },
  {
    code: "it_specialist", name: "Айтишник", subtitle: "Есть flowchart?",
    description: "Системное мышление. Хочет алгоритм, схему, процесс.",
    detailed_behavior: "\"А как это работает технически? Есть пошаговая схема?\" Мыслит процессами. Хочет видеть весь pipeline от начала до конца.",
    group: "professional", tier: 2, difficulty: 5, unlock_level: 5,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["cooperation"], counters: ["knowledge", "adaptation"],
    weakness: "Чёткий алгоритм: шаг 1 → шаг 2 → ... → результат",
  },
  {
    code: "government", name: "Чиновник", subtitle: "Какая нормативная база?",
    description: "Бюрократический подход. Нормативная база, регламенты.",
    detailed_behavior: "\"На основании какого закона? Какие подзаконные акты?\" Говорит на языке документов. Менеджер должен знать нормативную базу.",
    group: "professional", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["legal_traps"], counters: ["legal_knowledge", "knowledge"],
    weakness: "Точные ссылки на законы и постановления пленума",
  },
  {
    code: "journalist", name: "Журналист", subtitle: "А можно я запишу?",
    description: "Расследователь. Копает, уточняет, может записывать.",
    detailed_behavior: "\"А можно я запишу? А какой процент выигранных дел? А можно контакты ваших клиентов?\" Профессиональное любопытство + привычка проверять.",
    group: "professional", tier: 3, difficulty: 7, unlock_level: 8,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["information_warfare"], counters: ["adaptation", "stress_resistance", "legal_knowledge"],
    weakness: "Открытость: \"Записывайте. Вот наши цифры и факты\"",
  },
  {
    code: "psychologist", name: "Психолог", subtitle: "Вы используете НЛП?",
    description: "Анализирует каждый приём менеджера. Называет техники вслух.",
    detailed_behavior: "\"О, рефрейминг. Интересно.\" \"Это anchoring, да?\" Не враждебен — профессионально заинтересован. Хочет \"человеческий\" разговор без техник.",
    group: "professional", tier: 3, difficulty: 8, unlock_level: 9,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["information_warfare", "pride"], counters: ["adaptation", "stress_resistance", "rapport_building"],
    weakness: "Перестать использовать техники и говорить \"по-человечески\"",
  },
  {
    code: "competitor_employee", name: "Сотрудник конкурента", subtitle: "А почему не через МФЦ?",
    description: "Притворяется клиентом, собирает информацию о ценах и методах.",
    detailed_behavior: "Начинает как прагматик, потом задаёт подозрительно точные вопросы. Провоцирует критику конкурентов. Скрытый саботаж.",
    group: "professional", tier: 4, difficulty: 9, unlock_level: 11,
    color: "var(--text-muted)", icon: "\u{1F4BC}",
    tags: ["deception", "manipulation"], counters: ["adaptation", "stress_resistance", "qualification"],
    weakness: "Не вестись на провокации о конкурентах. Фокус на ситуации клиента.",
  },

  // ══════════════════════════════════════════════════════════════════════════
  // GROUP 10: COMPOUND (Гибриды) — 10 archetypes
  // ══════════════════════════════════════════════════════════════════════════
  {
    code: "aggressive_desperate", name: "Отчаянный агрессор", subtitle: "Кричит от безысходности",
    description: "aggressive + desperate: кричит не из злости, а от безысходности.",
    detailed_behavior: "Агрессия маскирует глубокое отчаяние. За криком — страх и боль. Менеджер должен \"пробить\" агрессию и достучаться до настоящей эмоции.",
    group: "compound", tier: 3, difficulty: 8, unlock_level: 8,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["yelling", "emotional_pressure", "crisis"], counters: ["stress_resistance", "empathy"],
    weakness: "\"Я слышу, что вы злитесь. Но мне кажется, за этим что-то большее...\"",
  },
  {
    code: "manipulator_crying", name: "Плачущий манипулятор", subtitle: "Слёзы как оружие",
    description: "manipulator + crying: использует слёзы как инструмент давления.",
    detailed_behavior: "Плачет, чтобы вызвать жалость и добиться уступок. Если менеджер проявляет эмпатию — переключается на требования. Двойной bind.",
    group: "compound", tier: 3, difficulty: 8, unlock_level: 8,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["emotional_pressure", "manipulation", "deception"], counters: ["stress_resistance", "objection_handling"],
    weakness: "Валидация чувств БЕЗ уступок: \"Я вижу что вам тяжело. Давайте обсудим что реально возможно\"",
  },
  {
    code: "know_it_all_paranoid", name: "Параноидальный всезнайка", subtitle: "Знаю всё + не верю никому",
    description: "know_it_all + paranoid: считает себя экспертом и не доверяет никому.",
    detailed_behavior: "\"Я всё изучил, и я знаю что вы врёте.\" Худшая комбинация: уверенность в своих знаниях + тотальное недоверие. Двойная стена.",
    group: "compound", tier: 3, difficulty: 8, unlock_level: 9,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["pride", "fear", "confrontation"], counters: ["knowledge", "legal_knowledge", "stress_resistance"],
    weakness: "Признание его знаний + документальное подтверждение каждого слова",
  },
  {
    code: "passive_aggressive", name: "Пассивно-агрессивный", subtitle: "Вежливый яд",
    description: "passive + sarcastic: формально вежлив, но каждое слово — яд.",
    detailed_behavior: "\"Конечно-конечно, вы же лучше знаете... Нет-нет, продолжайте, мне ОЧЕНЬ интересно.\" Двойное дно в каждой фразе.",
    group: "compound", tier: 3, difficulty: 7, unlock_level: 7,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["deception", "confrontation"], counters: ["stress_resistance", "adaptation"],
    weakness: "Прямое и спокойное называние: \"Я чувствую иронию. Давайте по-честному?\"",
  },
  {
    code: "couple_disagreeing", name: "Конфликтная пара", subtitle: "Ссорятся при менеджере",
    description: "couple + aggressive: пара, которая спорит МЕЖДУ СОБОЙ на звонке.",
    detailed_behavior: "Муж хочет банкротство, жена против (или наоборот). Спорят, перебивают друг друга. Менеджер — арбитр и медиатор.",
    group: "compound", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["yelling", "family"], counters: ["adaptation", "empathy", "stress_resistance"],
    weakness: "Найти ОБЩИЙ интерес пары и работать через него",
  },
  {
    code: "elderly_paranoid", name: "Пожилой параноик", subtitle: "Доченька, а вы точно не мошенники?",
    description: "elderly + paranoid: пожилой человек, боящийся мошенничества.",
    detailed_behavior: "\"А вы точно из юридической? А можно мне позвонить на ваш основной номер?\" Страх + непонимание + возрастные особенности.",
    group: "compound", tier: 4, difficulty: 9, unlock_level: 10,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["fear", "family"], counters: ["empathy", "rapport_building", "adaptation"],
    weakness: "Максимальная прозрачность + простые слова + терпение",
  },
  {
    code: "hysteric_litigious", name: "Истерик-сутяжник", subtitle: "Паника + угрозы судом",
    description: "hysteric + litigious: одновременно паникует и угрожает судом.",
    detailed_behavior: "\"ВСЁ ПРОПАЛО! Я ПОДАМ НА ВАС В СУД! А МОЖЕТ НЕТ! ПОМОГИТЕ!\" Хаотическое переключение между паникой и юридическими угрозами.",
    group: "compound", tier: 4, difficulty: 10, unlock_level: 12,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["yelling", "legal_traps", "emotional_pressure", "crisis"], counters: ["stress_resistance", "legal_knowledge", "empathy"],
    weakness: "Сначала стабилизировать эмоции, потом адресовать юридические вопросы",
  },
  {
    code: "puppet_master_lawyer", name: "Юрист-кукловод", subtitle: "Каскад юридических ловушек",
    description: "puppet_master + lawyer_client: каскад юридических вопросов-ловушек.",
    detailed_behavior: "Каждый вопрос — юридическая ловушка. Каскад из 3-5 связанных вопросов. Одна ошибка — цепная реакция. Высший пилотаж.",
    group: "compound", tier: 4, difficulty: 10, unlock_level: 13,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["legal_traps", "manipulation", "deception"], counters: ["legal_knowledge", "stress_resistance", "objection_handling"],
    weakness: "Распознать каскад и разорвать цепочку: \"Давайте разберём каждый вопрос отдельно\"",
  },
  {
    code: "shifting", name: "Хамелеон", subtitle: "Меняет архетип каждые 3-4 реплики",
    description: "Уникальный: случайная смена архетипа каждые 3-4 хода.",
    detailed_behavior: "Начинает как скептик → через 4 реплики тревожный → через 3 реплики манипулятор. Эмоция СОХРАНЯЕТСЯ. Ловушки НАКАПЛИВАЮТСЯ. Адаптируйся мгновенно.",
    group: "compound", tier: 4, difficulty: 10, unlock_level: 15,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["deception"], counters: ["adaptation", "stress_resistance", "empathy"],
    weakness: "Стабильная линия поведения менеджера вне зависимости от смен",
  },
  {
    code: "ultimate", name: "Абсолют", subtitle: "Финальный босс",
    description: "Все механики: FakeTransition, trap cascade, shifting, emotional spikes.",
    detailed_behavior: "Финальный босс. 3+ архетипов, все ловушки активны, фейковые переходы, каскады, time pressure. Boss mode, no hints. Легенда.",
    group: "compound", tier: 4, difficulty: 10, unlock_level: 19,
    color: "var(--accent)", icon: "\u{1F52E}",
    tags: ["yelling", "manipulation", "deception", "legal_traps", "emotional_pressure"], counters: ["adaptation", "stress_resistance", "empathy"],
    weakness: "Все навыки на максимуме — нет отдельной слабости",
  },
];

// ─── Helper Functions ───────────────────────────────────────────────────────

export function findArchetype(nameOrCode: string | null | undefined): ArchetypeInfo | undefined {
  if (!nameOrCode) return undefined;
  const lower = nameOrCode.toLowerCase().trim();
  return ARCHETYPES.find((a) => a.code === lower || a.name.toLowerCase() === lower);
}

/**
 * Try to extract archetype from scenario title.
 * Titles often follow pattern: "Холодный звонок — Скептик"
 */
export function findArchetypeFromTitle(title: string): ArchetypeInfo | undefined {
  const lower = title.toLowerCase();
  for (const a of ARCHETYPES) {
    if (lower.includes(a.name.toLowerCase())) return a;
  }
  const parts = title.split(/\s*[—–-]\s*/);
  if (parts.length >= 2) {
    const afterDash = parts[parts.length - 1].trim().toLowerCase();
    return ARCHETYPES.find((a) => afterDash.includes(a.name.toLowerCase()));
  }
  return undefined;
}

/** Get all archetypes for a group */
export function getArchetypesByGroup(group: ArchetypeGroup): ArchetypeInfo[] {
  return ARCHETYPES.filter((a) => a.group === group);
}

/** Get all archetypes for a tier */
export function getArchetypesByTier(tier: ArchetypeTier): ArchetypeInfo[] {
  return ARCHETYPES.filter((a) => a.tier === tier);
}

/** Get archetypes available at a given level */
export function getArchetypesForLevel(level: number): ArchetypeInfo[] {
  return ARCHETYPES.filter((a) => a.unlock_level <= level);
}

/** Get tier color */
export function getTierColor(tier: ArchetypeTier): string {
  switch (tier) {
    case 1: return "#7C6AE8"; // accent purple — baseline
    case 2: return "#9B7AE8"; // lighter purple — intermediate
    case 3: return "#B896F0"; // lavender — advanced
    case 4: return "#D4A84B"; // gold accent — expert (reward color)
  }
}

/** Difficulty colors — monochrome purple scale + gold for extreme */
export function getDifficultyColor(difficulty: number): string {
  if (difficulty <= 3) return "#7C6AE8"; // accent — easy
  if (difficulty <= 6) return "#9B7AE8"; // lighter — medium
  if (difficulty <= 8) return "#B896F0"; // lavender — hard
  return "#D4A84B"; // gold — extreme (reward/challenge)
}

/** Get tier label */
export function getTierLabel(tier: ArchetypeTier): string {
  switch (tier) {
    case 1: return "Tier 1 — Базовый";
    case 2: return "Tier 2 — Средний";
    case 3: return "Tier 3 — Сложный";
    case 4: return "Tier 4 — Экстремальный";
  }
}

/** Russian labels for English skill codes */
export const SKILL_LABELS: Record<string, string> = {
  objection_handling: "Возражения",
  stress_resistance: "Стрессоустойчивость",
  adaptation: "Адаптация",
  knowledge: "Экспертиза",
  rapport: "Контакт",
  script_adherence: "Скрипт",
  active_listening: "Слушание",
  empathy: "Эмпатия",
  negotiation: "Переговоры",
  closing: "Закрытие",
  patience: "Терпение",
  creativity: "Креативность",
  authority: "Авторитет",
  time_management: "Темп",
  professionalism: "Профессионализм",
  analytical: "Аналитика",
  emotional_intelligence: "EQ",
  persuasion: "Убеждение",
  conflict_resolution: "Конфликты",
  product_knowledge: "Продукт",
};

export function getSkillLabel(code: string): string {
  return SKILL_LABELS[code] || code.replace(/_/g, " ");
}
