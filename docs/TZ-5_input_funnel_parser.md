# ТЗ-5 — Input funnel: материалы → автокарточка сценария

> **Статус:** концепт. Идея от пользователя 2026-04-29. Rev. 2 после code audit.
> **Зависимости:** TZ-4 §7 (attachment_pipeline есть), TZ-3 (scenario lifecycle).
> **Триггер:** пользователь предложил «загрузить свои данные → платформа парсит → предлагает карточку сценария».
>
> ⚠️ **Корректировки rev. 2 (важные расширения scope):**
> - **PDF/DOCX парсера в API НЕТ.** `grep "pypdf|PyPDF2|python-docx|pdfplumber|unstructured"` → 0 hits. В `pyproject.toml` только `fpdf2` (writer, не reader). **Нужен новый dependency** + extraction-сервис. Это **расширяет scope**, не «лишь добавить ветку в classifier».
> - **Путь сценариев существует** через query-параметр: `/dashboard?tab=methodology&sub=scenarios` рендерит [ScenariosEditor.tsx](apps/web/src/components/dashboard/methodology/ScenariosEditor.tsx) (487 строк, TZ-3 §14.4 MVP). Что **уже** работает: список templates со status-badge + draft_revision + version indicator, кнопка Publish с обработкой 409/422, view-versions disclosure. Что **НЕ** в текущем MVP (явно расписано в docstring файла):
>   - **In-place editing** (name/description/stages) — «C4.1, ещё не в UI». Сейчас methodologists правят через `PUT /rop/scenarios/{id}` напрямую API.
>   - **Drag-and-drop reorder этапов**, traps picker, scoring modifier editor — «polish, не MVP».
>   - **Create-new wizard** — «C4.2, после того как Publish flow обкатается неделю».
> - Document-types в `attachment_storage.py:57-68` — **только 5 mime-категорий** (`pdf`, `image`, `document`, `spreadsheet`, `unknown`). Нет semantic typing. Нужен **второй уровень** классификации (semantic doc-type поверх mime).
> - «11 состояний» из rev. 1 — это была моя оценка. Реально в коде **4 ортогональных status-колонки** (`status` × `ocr_status` × `classification_status` × `verification_status`), декартово произведение даёт ≈11 валидных состояний — но это не зафиксированный invariant.

## 1. Зачем

Сейчас создание сценария — ручной процесс через `/dashboard/methodology/scenarios`. ROP/админ описывает шаги, реплики, ожидаемые возражения. Это барьер входа: чтобы платформа дала ценность новой команде, нужно потратить 2-4 часа на наполнение.

**Идея:** ROP загружает уже **существующие материалы** компании:
- Памятку для менеджера в .docx / .pdf
- Скрипты звонков в .txt / .docx
- Записи реальных удачных звонков (транскрипты)
- Презентации продукта в .pptx / .pdf

Платформа **парсит**, **извлекает** структуру, **предлагает черновик карточки сценария** (этапы, ключевые реплики, типичные возражения, ожидаемый успешный исход). ROP правит → публикует → у менеджеров появляется новый сценарий.

## 2. Что переиспользуем (TZ-4 D2)

`attachment_pipeline` уже умеет:
- Принимать файлы → SHA256 dedup
- Антивирус scan (`scanned`/`scan_failed`)
- OCR для PDF/изображений (`ocr_pending`/`ocr_done`)
- Классифицировать `document_type` (`classified`)
- Linking к `lead_client_id` (`linked`)
- Финальный `ready` state

Расширим: добавим **новый document_type** `"training_material"` и новый pipeline branch:
```
classified (document_type=training_material) →
  scenario_draft_extracting →
  scenario_draft_ready →
  linked (to scenario_template, not lead_client)
```

## 3. Архитектура

### 3.1 Новый сервис `scenario_extractor`

`app/services/scenario_extractor.py`

Вход: `attachment.id` (документ в state `classified` с типом `training_material`)
Выход: `ScenarioDraft` объект:

```python
@dataclass
class ScenarioDraft:
    title_suggested: str
    summary: str
    archetype_hint: str | None  # "недовольный должник", "скептик-руководитель"
    steps: list[ScenarioStep]
    expected_objections: list[str]
    success_criteria: list[str]
    quotes_from_source: list[str]  # для подтверждения "это не выдумка LLM"
    confidence: float
```

LLM-pipeline в две прохода:
1. **Извлечение структуры** — Claude Sonnet (нужно длинное окно), 1 вызов
2. **Валидация** — Haiku проверяет что `quotes_from_source` действительно содержатся в исходнике

### 3.2 UI flow

`/dashboard/methodology/scenarios/import` (новый surface):

1. ROP перетаскивает файл → видит progress bar по 11-state pipeline
2. Файл достигает `scenario_draft_ready` → появляется карточка предпросмотра
3. ROP правит черновик прямо на странице (как обычный editor)
4. Кнопка **«Создать сценарий»** → создаётся `scenario_template` + `scenario_version` (status=draft) → попадает в обычный TZ-3 flow
5. Дальше — обычная публикация через TZ-3 (Publish button → новые версии)

### 3.3 Связь с архетипами

Если в материале явно описан **типаж клиента** ("обычно звонит директор стройфирмы, агрессивный, торопится") → подбирать ближайший существующий archetype. Если ничего не подходит — **предлагать создать новый archetype** (отдельный flow).

## 4. Что НЕ делаем

- **НЕ автоматически публикуем** черновик. Все сценарии проходят через ROP review (TZ-3 invariant сохраняем).
- **НЕ доверяем LLM на 100%** — `confidence < 0.6` не показываем как готовый draft, выводим только raw extracted text «попробуйте сами структурировать».
- **НЕ принимаем видео/аудио** в первой итерации — только текст. Транскрипция → отдельный TZ.

## 5. Acceptance criteria

- [ ] ROP загружает .docx с памяткой → за ~30 секунд получает draft с 5+ шагами и 3+ возражениями
- [ ] Draft содержит **цитаты из исходника** для каждого шага (audit trail)
- [ ] Можно отредактировать draft до публикации (TZ-3 lifecycle)
- [ ] Опубликованный сценарий ничем не отличается от созданного вручную (TZ-3 invariant)
- [ ] Поддержка форматов: .pdf, .docx, .txt, .md, .pptx
- [ ] Файл больше 50 МБ → отказ с понятным сообщением
- [ ] Файл с PII клиентов → автоматическое замаскирование PII в draft (152-ФЗ)

## 6. Тесты

- `test_scenario_extractor.py` — golden tests на 10 reference материалов
- `test_attachment_pipeline_training_material.py` — новый branch не ломает существующие
- `test_scenario_draft_to_template.py` — конвертация draft → scenario_template
- E2E browser test: ROP загружает .docx → видит draft → публикует → manager видит сценарий

## 7. Риски

1. **LLM галлюцинации** в шагах сценария — митигируется обязательными quotes из исходника
2. **PII leak** в draft — нужен PII scrubber (TZ-4 §6 уже имеет)
3. **Качество разное по форматам** — .pdf с OCR хуже .docx; нужны warnings ROP'у
4. **152-ФЗ соответствие** загружаемых материалов — ROP должен подтвердить чек-боксом «этот материал можно использовать в обучении»

## 8. Объём работы (rev. 2 — реальные оценки после code audit)

- **Новые deps + PDF/DOCX парсер** (выбор + интеграция `pypdf` или `unstructured`): 2 дня
- **Расширить ScenariosEditor.tsx** до полного CRUD (in-place editing формы, create-new wizard) — то что в docstring помечено как «C4.1 + C4.2»: 3-4 дня. Эта часть **нужна в любом случае** для пилота, не только для import-flow.
- Backend `scenario_extractor` (+ pipeline branch): 5 дней
- FE drag-and-drop import + draft editor поверх существующего ScenariosEditor: 4 дня
- Тесты + golden references: 3 дня
- A/B с 3 пилотными командами: 1 неделя

Итого: **~3.5 недели** до запуска beta, потом 2-3 недели обкатки.

**Расщепление:**
- **TZ-5a — Полный CRUD сценариев в UI** (расширение `ScenariosEditor.tsx` до C4.1+C4.2 из docstring). Обязательно для пилота. ~4 дня.
- **TZ-5b — Import flow** (PDF/DOCX парсер + scenario_extractor + drag-drop UI поверх 5a). Можно после пилота. ~3 недели.

## 9. Связь с ареной (TZ-4.4 user request)

Пользователь упомянул «запусти агентов по арене». Логика связи:
- Часть загружаемых материалов содержат фактические данные (статьи 127-ФЗ, кейсы, цифры)
- Эти данные могут попадать **не в сценарий**, а в **arena content** (knowledge chunks для квиза)
- Расширение TZ-5: материал классифицируется на «scenario» vs «arena_knowledge» vs «mixed» → разные ветки.
- Arena_knowledge → существующий `LegalKnowledgeChunk` pipeline с TZ-4 §8 review queue.
