# Dead-code audit — `apps/web/src/components/training/` (2026-05-07)

Audit run as the «PR-2 ③ аудит мусорного кода» follow-up promised in
the original /training redesign plan. The Конструктор pipeline itself
is clean — no truly dead code paths found in the constructor → REST →
WebSocket → LLM-prompt chain (the deep audit on 2026-05-07 confirmed
all `custom_*` fields land on the LLM, the only «silent» bug was the
overwrite race fixed by PR-B/PR-F).

This document lists **leaf component orphans** under
`apps/web/src/components/training/` — files that compile and ship in
the bundle but no longer have any importer. Removing these is a
separate cleanup PR (out of scope here); the doc just makes the list
auditable so the user can decide what's safe to delete.

## Methodology

```
grep -rln 'import.*<Component>\b\|from .*<Component>"' apps/web/src apps/api
```

A component is flagged as orphan iff zero importers outside its own
defining file remain in the active source tree. Indirect references
(string literals, dynamic imports, lazy()) are NOT detected — anything
flagged here should be re-checked with a runtime feature-flag review
before deletion.

## Confirmed orphans (no static importer)

| File | LOC | Notes |
|---|---|---|
| `Avatar3D.tsx` | 348 | three.js / GLB avatar variant. The constructor and call page use `AvatarPreview` (DiceBear-based) instead. |
| `VRMAvatar.tsx` | 250 | `@pixiv/three-vrm` avatar variant with `// @ts-ignore` shims. The optional dep is documented as «may not be installed yet» — confirms this path is not exercised. |
| `TalkingHeadAvatar.tsx` | 195 | `@met4citizen/talkinghead` variant. Same story as VRMAvatar — installed dependency, no live consumer. |
| `ObjectionLibrary.tsx` | — | Pre-PR-D objection list display. Replaced by inline objection chips in `ScenarioCatalogCard`. |
| `CallButton.tsx` | — | Standalone call CTA. Comment in `[id]/page.tsx` (~L37) calls it «dormant»; inline buttons cover the use cases. |
| `ScenarioDossierCard.tsx` | — | Pre-redesign card style for `/training` Сценарии tab. Replaced by `ScenarioCatalogCard` in PR #275. |
| `PreSessionBrief.tsx` | — | Pre-Story-Mode brief overlay. Replaced by `PreCallBriefOverlay` (story-aware). |
| `StageProgress.tsx` | — | Standalone stage HUD. Stage progress is now rendered inline inside `PhoneCallMode` and the chat sidebar. |
| `InputBarMoreMenu.tsx` | — | Pre-PR-A input bar kebab menu. Confirmed dead by PR #234 commit message («new mode_switch icon»). |
| `TranscriptionIndicator.tsx` | — | Live STT chip. Replaced by `MicStatusBanner` (`MicBannerKind` enum covers all the prior states). |

## Active leaves (look orphan but are NOT)

These trigger the naive grep but ARE used via different import paths
or feature-gated:

| File | Why it stays |
|---|---|
| `IncomingCallScreen.tsx` | imported in `[id]/call/page.tsx` (verified — 1 importer). The naive grep missed the `phone/` subpath. |
| `StylizedAvatar.tsx` | imported in `[id]/page.tsx` via dynamic import with WebGL-failure fallback. |
| `phone/PhoneCallMode.tsx` | rendered in `[id]/call/page.tsx` main return. Same subpath issue as IncomingCallScreen. |
| `phone/CallDialingOverlay.tsx` | rendered in `[id]/call/page.tsx` overlay row. |
| `phone/CallEndingTransition.tsx` | rendered in `[id]/call/page.tsx` hangup branch. |
| `BetweenCallsOverlay.tsx` | rendered in `[id]/page.tsx` story-mode branch. |
| `SessionEndingOverlay.tsx` | rendered in `[id]/page.tsx` end branch. |
| `ScriptPanel.tsx` | rendered in `[id]/page.tsx` script panel. |

## Recommendation

Delete the 10 confirmed orphans in a separate PR. Estimated savings:
~1500-2000 LOC + 3 npm dependencies (`@pixiv/three-vrm`,
`@met4citizen/talkinghead`, `three`) if no other call site emerges.
The avatar variants in particular have been quietly carried since the
2026-04 «3D avatar exploration» wave; the project landed on
`AvatarPreview` (DiceBear pixel art) and never circled back to
delete the alternatives.

## Backend pipeline — no dead code found

The backend audit by the Opus subagent on 2026-05-07 traced all 14
`custom_*` fields end-to-end. None were silently dropped after the
PR-B/F/B2 series:

- `custom_session_mode` → alive (`api/training.py:340` normalizes via
  `normalize_session_mode`, also on `:437`, `:454`, `:633`).
- `custom_tone` → alive at runtime via
  `client_generator.generate_personality_profile`, AND in
  `ClientStory` baseline via PR-B2 `apply_tone_ocean_shift`.
- `custom_emotion_preset`, `custom_bg_noise`, `custom_time_of_day`,
  `custom_fatigue`, `custom_debt_stage` → alive every-call via
  `_build_client_profile_prompt(ambient_ctx=custom_params)`.
- `custom_archetype`, `custom_profession`, `custom_lead_source`,
  `custom_difficulty`, `custom_family_preset`, `custom_creditors_preset`,
  `custom_debt_range` → alive via the cloned `ClientProfile`.

The largest «silently broken» path was the
`state["client_profile_prompt"]` overwrite race that PR-B/F closed.
That's now covered by 9 regression tests in
`apps/api/tests/test_between_call_intelligence.py::TestBetweenCallAppendixConsumption`.
