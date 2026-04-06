/**
 * Navigator quotes library — client-side mirror of backend.
 * 84 quotes × 11 categories, rotating every 6 hours.
 *
 * Slot logic (same as backend):
 *   slot       = floor(utcHour / 6)          → 0–3
 *   dayNumber  = floor(unixMs / 86_400_000)  → days since epoch
 *   index      = (dayNumber * 4 + slot) % TOTAL
 */

export interface NavQuote {
  text: string;
  author: string;
  source: string;
  category: string;
  category_label: string;
}

export const CATEGORY_LABELS: Record<string, string> = {
  negotiations:  "Переговоры и влияние",
  sales:         "Продажи и убеждение",
  psychology:    "Психология влияния",
  strategy:      "Стратегическое мышление",
  leadership:    "Лидерство",
  law:           "Право и аргументация",
  discipline:    "Дисциплина и продуктивность",
  money:         "Деньги, капитал, власть",
  mindset:       "Психология успеха",
  communication: "Коммуникация и присутствие",
  extreme:       "Экстремальный контекст",
};

export const QUOTES: NavQuote[] = [
  // I. Переговоры и влияние (8)
  { text: "Никогда не позволяйте другой стороне знать, что вам нужна сделка. Тот, кто больше нуждается — проигрывает.", author: "Джим Кэмп", source: "Сначала скажите НЕТ", category: "negotiations", category_label: "Переговоры и влияние" },
  { text: "Самая мощная позиция на переговорах — готовность уйти.", author: "Роджер Доусон", source: "", category: "negotiations", category_label: "Переговоры и влияние" },
  { text: "Тот, кто контролирует повестку — контролирует исход.", author: "Генри Киссинджер", source: "", category: "negotiations", category_label: "Переговоры и влияние" },
  { text: "Переговоры — это не соревнование. Это совместное решение проблемы, в котором у вас разные интересы.", author: "Роджер Фишер", source: "Путь к согласию", category: "negotiations", category_label: "Переговоры и влияние" },
  { text: "Молчание — самый мощный инструмент переговорщика. Большинство людей не выносят паузы и заполняют её уступками.", author: "Крис Восс", source: "Никаких компромиссов", category: "negotiations", category_label: "Переговоры и влияние" },
  { text: "Никогда не делайте предложение первым, если не знаете диапазон противника.", author: "Крис Восс", source: "", category: "negotiations", category_label: "Переговоры и влияние" },
  { text: "Люди не покупают логику. Они покупают эмоцию и обосновывают её логикой.", author: "Зиг Зиглар", source: "", category: "negotiations", category_label: "Переговоры и влияние" },
  { text: "Позвольте другой стороне говорить. Информация — это власть.", author: "Дэниел Канеман", source: "", category: "negotiations", category_label: "Переговоры и влияние" },
  // II. Продажи и убеждение (8)
  { text: "Продажа происходит, когда клиент убеждает себя сам. Ваша задача — задать правильные вопросы.", author: "Нил Рэкхэм", source: "СПИН-продажи", category: "sales", category_label: "Продажи и убеждение" },
  { text: "Возражение — это не отказ. Это запрос на дополнительную информацию.", author: "Брайан Трейси", source: "", category: "sales", category_label: "Продажи и убеждение" },
  { text: "Люди покупают у тех, кому доверяют. Доверие строится медленно, разрушается мгновенно.", author: "Уоррен Баффет", source: "", category: "sales", category_label: "Продажи и убеждение" },
  { text: "Ценность — это не то, что вы предлагаете. Это то, что клиент считает ценным.", author: "Нил Рэкхэм", source: "", category: "sales", category_label: "Продажи и убеждение" },
  { text: "Единственный способ влиять на людей — говорить им о том, чего они хотят, и показывать, как это получить.", author: "Дейл Карнеги", source: "Как завоёвывать друзей", category: "sales", category_label: "Продажи и убеждение" },
  { text: "Прежде чем продавать — продайте себя.", author: "Наполеон Хилл", source: "", category: "sales", category_label: "Продажи и убеждение" },
  { text: "Цена никогда не является реальным возражением. За ней всегда скрывается отсутствие воспринимаемой ценности.", author: "Брайан Трейси", source: "", category: "sales", category_label: "Продажи и убеждение" },
  { text: "Самый опасный момент в продаже — когда вы думаете, что уже победили.", author: "Дэвид Сэндлер", source: "", category: "sales", category_label: "Продажи и убеждение" },
  // III. Психология влияния (8)
  { text: "Человек, которому сделали одолжение, с большей вероятностью сделает одолжение в ответ, чем тот, кому помогли.", author: "Бенджамин Франклин", source: "Эффект Франклина", category: "psychology", category_label: "Психология влияния" },
  { text: "Последовательность — это тюрьма, в которую большинство людей заходят добровольно.", author: "Роберт Чалдини", source: "Психология влияния", category: "psychology", category_label: "Психология влияния" },
  { text: "Люди следуют за авторитетом. Сначала продемонстрируйте экспертность — потом делайте запрос.", author: "Роберт Чалдини", source: "", category: "psychology", category_label: "Психология влияния" },
  { text: "Дефицит создаёт ценность. Всё, что редко — желанно.", author: "Роберт Чалдини", source: "", category: "psychology", category_label: "Психология влияния" },
  { text: "Никто не принимает решения на основе фактов. Все принимают решения на основе чувств и ищут факты в подтверждение.", author: "Антонио Дамасио", source: "Ошибка Декарта", category: "psychology", category_label: "Психология влияния" },
  { text: "Фрейминг важнее содержания. Одно и то же можно подать как потерю или как выгоду — реакция будет полностью разной.", author: "Даниэль Канеман", source: "Думай медленно, решай быстро", category: "psychology", category_label: "Психология влияния" },
  { text: "Люди в 2,5 раза сильнее мотивированы избежать потери, чем получить эквивалентную выгоду.", author: "Даниэль Канеман / Амос Тверски", source: "Теория перспектив", category: "psychology", category_label: "Психология влияния" },
  { text: "Якорение работает всегда. Первое названное число формирует всё последующее восприятие диапазона.", author: "Даниэль Канеман", source: "", category: "psychology", category_label: "Психология влияния" },
  // IV. Стратегическое мышление (8)
  { text: "Если вы знаете врага и знаете себя — вам не нужно бояться результата ста сражений.", author: "Сунь-цзы", source: "Искусство войны", category: "strategy", category_label: "Стратегическое мышление" },
  { text: "Лучшая победа — та, в которой не нужно сражаться.", author: "Сунь-цзы", source: "Искусство войны", category: "strategy", category_label: "Стратегическое мышление" },
  { text: "Стратегия без тактики — самый медленный путь к победе. Тактика без стратегии — шум перед поражением.", author: "Сунь-цзы", source: "", category: "strategy", category_label: "Стратегическое мышление" },
  { text: "Не реагируйте на ситуацию — формируйте её заранее.", author: "Никколо Макиавелли", source: "Государь", category: "strategy", category_label: "Стратегическое мышление" },
  { text: "Тот, кто умеет предвидеть трудности и устранять их заблаговременно, непобедим.", author: "Никколо Макиавелли", source: "", category: "strategy", category_label: "Стратегическое мышление" },
  { text: "В игре без правил побеждает тот, кто сам устанавливает правила.", author: "Роберт Грин", source: "48 законов власти", category: "strategy", category_label: "Стратегическое мышление" },
  { text: "Никогда не демонстрируйте всё своё мастерство сразу. Всегда оставляйте что-то, чего о вас не знают.", author: "Роберт Грин", source: "48 законов власти", category: "strategy", category_label: "Стратегическое мышление" },
  { text: "Делайте работу, оставаясь в тени, и управляйте теми, кто на виду.", author: "Роберт Грин", source: "", category: "strategy", category_label: "Стратегическое мышление" },
  // V. Лидерство (7)
  { text: "Скорость лидера определяет скорость группы.", author: "Мэри Кэй Эш", source: "", category: "leadership", category_label: "Лидерство" },
  { text: "Управлять — значит работать через других, а не вместо них.", author: "Питер Друкер", source: "", category: "leadership", category_label: "Лидерство" },
  { text: "Великие лидеры не производят последователей. Они производят других лидеров.", author: "Том Питерс", source: "", category: "leadership", category_label: "Лидерство" },
  { text: "Разница между менеджером и лидером: менеджер делает вещи правильно, лидер делает правильные вещи.", author: "Питер Друкер", source: "", category: "leadership", category_label: "Лидерство" },
  { text: "Ваша задача как лидера — не быть правым. Ваша задача — получить правильный результат.", author: "Джек Уэлч", source: "", category: "leadership", category_label: "Лидерство" },
  { text: "Окружайте себя теми, кто лучше вас в конкретных задачах. Это и есть сила, не слабость.", author: "Эндрю Карнеги", source: "", category: "leadership", category_label: "Лидерство" },
  { text: "Люди уходят не из компаний. Они уходят от руководителей.", author: "Маркус Бакингем", source: "", category: "leadership", category_label: "Лидерство" },
  // VI. Право и аргументация (8)
  { text: "Закон без зубов — это просто совет.", author: "Афоризм англосаксонской школы права", source: "", category: "law", category_label: "Право и аргументация" },
  { text: "Тот, кто определяет термины — выигрывает спор.", author: "Аристотель", source: "", category: "law", category_label: "Право и аргументация" },
  { text: "Слабый аргумент, произнесённый уверенно, часто побеждает сильный аргумент, произнесённый с колебанием.", author: "Цицерон", source: "", category: "law", category_label: "Право и аргументация" },
  { text: "Судите о намерениях по действиям, не по словам.", author: "Цицерон", source: "", category: "law", category_label: "Право и аргументация" },
  { text: "Закон — это разум без страсти.", author: "Аристотель", source: "", category: "law", category_label: "Право и аргументация" },
  { text: "Истина редко бывает чистой и никогда простой.", author: "Оскар Уайльд", source: "", category: "law", category_label: "Право и аргументация" },
  { text: "Дайте мне шесть строчек, написанных рукой самого честного человека, и я найду в них что-нибудь, за что его можно повесить.", author: "Кардинал Ришельё", source: "", category: "law", category_label: "Право и аргументация" },
  { text: "В суде побеждает не тот, кто прав. Побеждает тот, кто лучше подготовлен.", author: "Афоризм юридической практики", source: "", category: "law", category_label: "Право и аргументация" },
  // VII. Дисциплина (8)
  { text: "Мотивация — это то, что вас запускает. Привычка — то, что вас движет.", author: "Джим Рон", source: "", category: "discipline", category_label: "Дисциплина и продуктивность" },
  { text: "Не ищите мотивацию. Создайте систему, которая работает без неё.", author: "Джеймс Клир", source: "Атомные привычки", category: "discipline", category_label: "Дисциплина и продуктивность" },
  { text: "Вы не поднимаетесь до уровня своих целей. Вы опускаетесь до уровня своих систем.", author: "Джеймс Клир", source: "Атомные привычки", category: "discipline", category_label: "Дисциплина и продуктивность" },
  { text: "Дисциплина — это мост между целями и достижениями.", author: "Джим Рон", source: "", category: "discipline", category_label: "Дисциплина и продуктивность" },
  { text: "Труднее всего начать действовать. Всё остальное зависит только от настойчивости.", author: "Амелия Эрхарт", source: "", category: "discipline", category_label: "Дисциплина и продуктивность" },
  { text: "Средний человек работает достаточно, чтобы не быть уволенным. Средняя компания платит достаточно, чтобы сотрудник не уволился.", author: "Джордж Карлин", source: "", category: "discipline", category_label: "Дисциплина и продуктивность" },
  { text: "Чем больше я тренируюсь, тем удачливее становлюсь.", author: "Гэри Плейер", source: "", category: "discipline", category_label: "Дисциплина и продуктивность" },
  { text: "Профессионал — это любитель, который не бросил.", author: "Ричард Бах", source: "", category: "discipline", category_label: "Дисциплина и продуктивность" },
  // VIII. Деньги, капитал, власть (6)
  { text: "Правило номер один: никогда не теряй деньги. Правило номер два: никогда не забывай правило номер один.", author: "Уоррен Баффет", source: "", category: "money", category_label: "Деньги, капитал, власть" },
  { text: "Время — более ценный ресурс, чем деньги. Потерянные деньги можно вернуть, потерянное время — нет.", author: "Майкл Лебёф", source: "", category: "money", category_label: "Деньги, капитал, власть" },
  { text: "Богатые люди строят сети. Все остальные ищут работу.", author: "Роберт Кийосаки", source: "", category: "money", category_label: "Деньги, капитал, власть" },
  { text: "Деньги — это просто инструмент. Они приведут вас туда, куда вы хотите, но не заменят вас в качестве водителя.", author: "Айн Рэнд", source: "", category: "money", category_label: "Деньги, капитал, власть" },
  { text: "Власть — это не то, что вам дают. Это то, что у вас забирают.", author: "Мао Цзэдун", source: "", category: "money", category_label: "Деньги, капитал, власть" },
  { text: "Тот, кто контролирует информацию, контролирует власть.", author: "Фрэнсис Бэкон", source: "Знание — сила", category: "money", category_label: "Деньги, капитал, власть" },
  // IX. Психология успеха (8)
  { text: "Вы не можете изменить то, с чем не готовы встретиться лицом к лицу.", author: "Джеймс Болдуин", source: "", category: "mindset", category_label: "Психология успеха" },
  { text: "Если вы думаете, что справитесь — вы правы. Если думаете, что не справитесь — вы тоже правы.", author: "Генри Форд", source: "", category: "mindset", category_label: "Психология успеха" },
  { text: "Разум — это всё. Вы становитесь тем, о чём думаете.", author: "Будда", source: "", category: "mindset", category_label: "Психология успеха" },
  { text: "Проблема не в проблеме. Проблема в вашем отношении к проблеме.", author: "Карл Юнг", source: "", category: "mindset", category_label: "Психология успеха" },
  { text: "Человек, у которого есть «зачем», выдержит почти любое «как».", author: "Фридрих Ницше", source: "", category: "mindset", category_label: "Психология успеха" },
  { text: "Самая большая тюрьма, в которой живут люди — это страх того, что думают другие.", author: "Дэвид Айк", source: "", category: "mindset", category_label: "Психология успеха" },
  { text: "Боль временна. Сдаться длится вечно.", author: "Лэнс Армстронг", source: "", category: "mindset", category_label: "Психология успеха" },
  { text: "Не жалуйтесь на то, что происходит. Это отнимает энергию от изменений.", author: "Тони Роббинс", source: "", category: "mindset", category_label: "Психология успеха" },
  // X. Коммуникация (8)
  { text: "Самое важное в коммуникации — услышать то, что не было сказано.", author: "Питер Друкер", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  { text: "Говорите только тогда, когда это улучшает тишину.", author: "Марк Твен", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  { text: "Речь — серебро, молчание — золото, в переговорах же молчание — бриллиант.", author: "Томас Карлейль", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  { text: "Тот, кто слушает — управляет разговором.", author: "Афоризм переговорной школы", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  { text: "Простота — высшая степень сложности.", author: "Леонардо да Винчи", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  { text: "Если вы не можете объяснить это просто — вы не понимаете это достаточно хорошо.", author: "Альберт Эйнштейн", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  { text: "Слова имеют вес только тогда, когда за ними стоят действия.", author: "Конфуций", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  { text: "Человека можно убедить только тогда, когда он чувствует, что его поняли.", author: "Карл Роджерс", source: "", category: "communication", category_label: "Коммуникация и присутствие" },
  // XI. Экстремальный контекст (7)
  { text: "Под давлением вы не поднимаетесь до своих ожиданий — вы падаете до своего уровня подготовки.", author: "Navy SEALs", source: "Стандарт спецназа ВМС США", category: "extreme", category_label: "Экстремальный контекст" },
  { text: "Кто не рискует — тот не пьёт шампанского.", author: "Русская поговорка", source: "", category: "extreme", category_label: "Экстремальный контекст" },
  { text: "Атакуй когда враг не ожидает, появись там, где тебя не ждут.", author: "Сунь-цзы", source: "Искусство войны", category: "extreme", category_label: "Экстремальный контекст" },
  { text: "Если противник превосходит тебя в силе — измотай его. Если равен — избегай прямого столкновения.", author: "Сунь-цзы", source: "", category: "extreme", category_label: "Экстремальный контекст" },
  { text: "Удача благоволит подготовленным.", author: "Луи Пастер", source: "", category: "extreme", category_label: "Экстремальный контекст" },
  { text: "Я не проиграл 10 000 раз. Я нашёл 10 000 способов, которые не работают.", author: "Томас Эдисон", source: "", category: "extreme", category_label: "Экстремальный контекст" },
  { text: "Либо найди путь, либо создай его.", author: "Ганнибал Барка", source: "", category: "extreme", category_label: "Экстремальный контекст" },
];

export const TOTAL_QUOTES = QUOTES.length;

/** Compute the current navigator quote from client-side data. */
export function getClientNavigator(): {
  quote: NavQuote;
  index: number;
  slot: number;
  secondsRemaining: number;
} {
  const now = new Date();
  const utcH = now.getUTCHours();
  const slot = Math.floor(utcH / 6);
  const dayNumber = Math.floor(now.getTime() / 86_400_000);
  const index = (dayNumber * 4 + slot) % TOTAL_QUOTES;

  // Next slot time
  const nextSlotH = (slot + 1) * 6;
  const nextSlot = new Date(now);
  nextSlot.setUTCMinutes(0, 0, 0);
  if (nextSlotH < 24) {
    nextSlot.setUTCHours(nextSlotH);
  } else {
    nextSlot.setUTCDate(nextSlot.getUTCDate() + 1);
    nextSlot.setUTCHours(0);
  }
  const secondsRemaining = Math.max(0, Math.floor((nextSlot.getTime() - now.getTime()) / 1000));

  return { quote: QUOTES[index], index, slot, secondsRemaining };
}
