# Worker B — W1 Manuscript Generation Report

**Date:** 2026-06-01
**Branch:** `codex/w1-orchestrated-import-quality`
**Worker:** B — W1 Manuscript Chapter Enrichment

---

## Summary

`node_build_manuscript()` now populates `summary`, `goal`, `notes`, and `chapterNumber` for every chapter it produces. These fields are written to `manuscript_chapters` in state before `node_write_to_project()` runs, so the proposal and split-file writer no longer has to fall back to first-220-char truncation.

---

## Fields Generated

| Field | Description | Generation Method |
|-------|-------------|-------------------|
| `summary` | 1–2 sentence chapter synopsis | `_chapter_summary_fallback()`: first paragraph (≤150 chars) + last paragraph (≤100 chars) joined with `……` for Chinese multi-paragraph; first-paragraph truncation for English/short text. No LLM. |
| `goal` | Writer-facing chapter purpose | Template string with detected character names from `entity_registry.characters`. Chinese: `梳理本章正文，核查{chars}等人物出场及事件与设定引用。` / fallback `梳理本章导入正文，核对人物、事件与设定引用。` |
| `notes` | Source provenance trace | `Imported from: {source_file_path}\nChunks: {chunk_ids}` + extraction warnings if present |
| `chapterNumber` | Parsed integer chapter number | `_detect_chapter_number()`: matches `第N章` (Arabic/Chinese numerals) and `Chapter N` (English). Returns `None` for untitled or non-numeric chapters. |

---

## New Helper Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `_ZH_NUM_MAP` | `w1_import.py:596` | Constant: Chinese digit → integer |
| `_parse_zh_number(s)` | `w1_import.py:606` | Converts Chinese number string to int |
| `_detect_chapter_number(title)` | `w1_import.py:621` | Parses chapter number from title |
| `_chapter_summary_fallback(text, lang, max)` | `w1_import.py:633` | Deterministic first+last paragraph extraction |

---

## Sample Before/After

**Before** — chapter dict from `node_build_manuscript()`:
```json
{
  "chapter_id": "chap_abc12345",
  "title": "第一章",
  "chunk_ids": [1],
  "manuscript_content": "韩立出生在一个普通家庭...",
  "orderIndex": 0
}
```

**After** — with enrichment:
```json
{
  "chapter_id": "chap_abc12345",
  "title": "第一章",
  "chunk_ids": [1],
  "manuscript_content": "韩立出生在一个普通家庭...",
  "orderIndex": 0,
  "summary": "韩立出生在一个普通家庭。父母务农为生。……他从小聪明好学，对修仙世界充满向往。",
  "goal": "梳理本章正文，核查韩立等人物出场及事件与设定引用。",
  "notes": "Imported from: /data/fanren.txt\nChunks: 1",
  "chapterNumber": 1
}
```

---

## TypedDict Update

`sidecar/models/state.py`: `ManuscriptChapter` split into `_ManuscriptChapterRequired` (4 required fields) + `ManuscriptChapter(_ManuscriptChapterRequired, total=False)` with optional `summary`, `goal`, `notes`, `chapterNumber`, `orderIndex`.

---

## Tests Run

```
sidecar/.venv/bin/python -m pytest tests/test_w1_import_compiler.py -q
58 passed in 1.61s
```

**Previous baseline:** 52 tests.  
**New tests added:** 6.

| New Test | Verifies |
|----------|---------|
| `test_parse_zh_number` | Chinese numeral → int conversion (7 cases) |
| `test_detect_chapter_number` | Title pattern matching (7 cases incl. Arabic/Chinese/English/None) |
| `test_chapter_summary_fallback` | Single paragraph, multi-paragraph Chinese ellipsis join, empty, English |
| `test_node_build_manuscript_enriches_chapters` | End-to-end: 2-chapter fixture has non-empty summary/goal/notes, correct chapterNumber |
| `test_node_build_manuscript_goal_includes_detected_characters` | Goal includes known character names when entity_registry populated |
| `test_node_build_manuscript_notes_includes_warnings` | Extraction errors from state["errors"] appear in notes |

---

## Files Modified

| File | Change |
|------|--------|
| `sidecar/models/state.py` | Extended `ManuscriptChapter` TypedDict with optional enrichment fields |
| `sidecar/workflows/w1_import.py` | Added `_ZH_NUM_MAP`, `_parse_zh_number`, `_detect_chapter_number`, `_chapter_summary_fallback`; enriched both chapter-building paths in `node_build_manuscript()` via `_enrich_chapter()` closure |
| `tests/test_w1_import_compiler.py` | Added 6 new tests |

---

## Remaining Risks

1. **Dense wall-text chapters** (no `\n\n` paragraph breaks): `_chapter_summary_fallback` returns only the first-paragraph truncation. Quality depends on source formatting.
2. **Goal character detection** is naive substring matching — a character named `韩` would match text containing `韩立`. Acceptable for now; a future pass could use exact word-boundary checks.
3. **`node_write_to_project()` fallback** (`_chapter_excerpt(manuscript_content, 220)`) is still present at line 4179 as a last resort. It will only be triggered for chapters that somehow bypass `node_build_manuscript()` (e.g., externally injected state). This is an acceptable defensive fallback.
4. **Worker A dependency**: These fields are written into split-file `writing/chapters/*.json` via `node_write_to_project()`, but Worker A (frontend loader) must hydrate those files into Zustand state before the UI can show them.
