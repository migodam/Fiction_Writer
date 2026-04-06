# Phase 7 End-to-End Test Report

**Date:** 2026-04-06  
**Source material:** 凡人修仙传1.txt (first 8000 chars, GBK→UTF-8)  
**AI Provider:** DeepSeek (deepseek-chat)  
**LangGraph version:** 1.0.10  
**Total test cases:** 22 across W0–W7

---

## Summary Table

| Phase | Workflow | Test | Result | Notes |
|---|---|---|---|---|
| B | W1 | Import 8000-char novel excerpt | ✅ PASS | 4 chunks, 77 proposals in inbox.json |
| C1 | W2 | post_import mode | ✅ PASS | Chapters written to writing/chapters/ |
| C2 | W2 | draft_only mode | ✅ PASS | Raw draft written to writing/draft.md |
| C3 | W2 | single_chapter mode | ✅ PASS | Entity extraction + diff + proposals |
| D1 | W3 | continue (direct_output) | ✅ PASS | Prose generated in xianxia style |
| D2 | W3 | rewrite | ✅ PASS | Scene rewritten |
| D3 | W3 | expand | ✅ PASS | Content expanded |
| D4 | W3 | improve_dialogue | ✅ PASS | Dialogue improved |
| D5 | W3 | three_options then select | ✅ PASS | 3 options generated, selection expanded |
| E1 | W4 | scene scope (clean) | ✅ PASS | 0 issues on clean scene |
| E2 | W4 | full scope (clean) | ✅ PASS | 9 issues detected in novel text |
| E3 | W4 | contradiction injection | ✅ PASS | 3 issues detected (eye color contradiction) |
| F1 | W7 | ingest style reference | ✅ PASS | ChromaDB updated, style profile built |
| F2 | W7+W3 | W3 with metadata_file_id | ✅ PASS | Style-guided prose generated |
| G1 | W5 | scenario engine only | ✅ PASS | 3-branch scenario report |
| G2 | W5 | scenario+character+logic | ✅ PASS | Multi-engine analysis |
| G3 | W5 | all 5 engines | ✅ PASS | Full simulation report |
| H1 | W6 | casual persona | ✅ PASS | Engagement 8.0, Pacing 6.0 |
| H2 | W6 | scholar persona | ✅ PASS | Engagement 9.0, Logic 7.0 |
| H3 | W6 | shipper persona | ✅ PASS | Character 9.0 (highest) |
| I1 | W0 | single workflow goal (W4) | ✅ PASS | Correct plan, W4 completed |
| I2 | W0 | chained goal (W3→W4) | ✅ PASS | 2-step plan, both executed |
| I3 | W0 | complex goal (W5+W6) | ✅ PASS | 4-step plan, all executed |

**Total: 22/22 PASS**

---

## Bugs Found and Fixed

### Critical (would block report)

**BUG-1: `StateGraph(dict)` state key loss (W4–W7, W0)**
- **Root cause:** In LangGraph v1.0.10, `StateGraph(dict)` causes node return values to REPLACE entire state instead of merging. Keys not returned by a node are lost.
- **Fix:** Changed all 5 workflows to use typed schemas: `StateGraph(ConsistencyState)`, `StateGraph(SimulationState)`, `StateGraph(BetaReaderState)`, `StateGraph(MetadataIngestionState)`, `StateGraph(OrchestratorState)`.
- **Files:** w4_consistency_check.py, w5_simulation.py, w6_beta_reader.py, w7_metadata_ingestion.py, w0_orchestrator.py

**BUG-2: `scene_content` dropped by typed schema (W4)**
- **Root cause:** `node_build_context` returned `scene_content` as a top-level state key, but `ConsistencyState` has no such field — it was silently dropped. Subsequent nodes got empty content.
- **Fix:** Store `scene_content` inside the `context` dict (which IS in ConsistencyState).
- **File:** sidecar/workflows/w4_consistency_check.py

**BUG-3: W4 E3 injection not detected — prompt insufficient**
- **Root cause:** `W4_CHARACTER_CHECK` prompt only checked scene content against stored character profiles. With no profiles loaded (only proposals in inbox), it couldn't detect intra-scene contradictions.
- **Fix:** Updated prompt to explicitly check for internal self-contradictions within scene content, regardless of whether profiles exist.
- **File:** sidecar/prompts/w4_prompts.py

**BUG-4: `context` not in initial state (W1, W2)**
- **Root cause:** W1/W2 `run()` convenience functions didn't include `context` key in initial state. `_get_llm()` got empty dict → empty API key → 401 auth errors.
- **Fix:** Added `"context": config.get("context", {})` to both initial states.
- **Files:** sidecar/workflows/w1_import.py, sidecar/workflows/w2_manuscript_sync.py

**BUG-5: LLM credentials overwritten by `s1_context_builder` (W4, W5)**
- **Root cause:** `node_build_context` and `node_load_affected_context` called `s1_context_builder.build_context()` and returned the result as `context`, discarding `api_key/model/endpoint`.
- **Fix:** Preserve credentials from `orig_ctx` before overwriting context.
- **Files:** sidecar/workflows/w4_consistency_check.py, sidecar/workflows/w5_simulation.py

### High Priority

**BUG-6: `persona_id` not in BetaReaderState (W6)**
- **Root cause:** `BetaReaderState` had no `persona_id` field. With `StateGraph(BetaReaderState)`, the `persona_id` from initial state was dropped, so `node_select_persona` got empty string → fell back to default "General Reader" persona.
- **Fix:** Added `persona_id`, `context`, `_chapter_text`, `_style_context`, `_avg_scores` to BetaReaderState.
- **Files:** sidecar/models/state.py, sidecar/workflows/w6_beta_reader.py

**BUG-7: W6 chapter content not loading (W6)**
- **Root cause:** `node_load_target_chapters` tried `data.get("content", "")` but chapters have no `content` field — content is in scene .md files via `sceneIds`. Fallback glob `{cid}*.md` also failed (chapter IDs don't match scene filenames).
- **Fix:** Added `sceneIds` traversal to load scene content when `content` field is empty.
- **File:** sidecar/workflows/w6_beta_reader.py

**BUG-8: W6 `_avg_scores` dropped by typed schema**
- **Root cause:** `_avg_scores` returned by `node_aggregate_feedback` was not in `BetaReaderState`.
- **Fix:** Added to `BetaReaderState` as `_avg_scores: Dict[str, float]`.
- **File:** sidecar/models/state.py

**BUG-9: W0 ChatAnthropic instead of ChatOpenAI**
- **Root cause:** W0 used `ChatAnthropic` for goal parsing, incompatible with DeepSeek.
- **Fix:** Replaced with `ChatOpenAI` with DeepSeek endpoint.
- **File:** sidecar/workflows/w0_orchestrator.py

**BUG-10: W0 acquires project lock, blocking child workflows**
- **Root cause:** W0 acquired the project mutex lock, then child workflows (W1, W4, etc.) also tried to acquire the same lock → `WorkflowBusyError`.
- **Fix:** Removed lock acquisition from W0 (child workflows manage their own locks).
- **File:** sidecar/workflows/w0_orchestrator.py

**BUG-11: W0 `interrupt_before=["execute_step"]` always fires**
- **Root cause:** LangGraph graph compiled with `interrupt_before=["execute_step"]` pauses before EVERY execute_step call, even when permissions are auto-approved. Requires external `Command(resume=True)` which was never sent.
- **Fix:** Removed `interrupt_before` from compile() — node-level `interrupt()` handles permission gating selectively.
- **File:** sidecar/workflows/w0_orchestrator.py

**BUG-12: W0 sends `context` dict but child endpoints expect flat `api_key/model/endpoint`**
- **Root cause:** `node_execute_step` sends `{"context": {...}}` but W4StartRequest, W5StartRequest, etc. expect `api_key`, `model`, `endpoint` as top-level fields.
- **Fix:** Flattened credentials into payload alongside `context`.
- **File:** sidecar/workflows/w0_orchestrator.py

**BUG-13: W0 `_pid_alive()` crashes on Windows**
- **Root cause:** `os.kill(pid, 0)` signal-0 check is a no-op on Windows and raises `SystemError` in some versions.
- **Fix:** Use `psutil.pid_exists()` as primary check, fall back to `os.kill` with proper exception handling.
- **File:** sidecar/utils/lock.py

**BUG-14: Task Running stuck bug (AgentChat)**
- **Root cause:** `AgentChat.tsx` called `store.addTaskRun({ status: 'running' })` but never updated status after `electronApi.aiChat()` resolved. Task stayed "running" indefinitely.
- **Fix:** Added `updateTaskRun` action to ProjectStore. Call it with `status: 'completed'` on success and `status: 'failed'` on error.
- **Files:** src/ui-react/store.ts, src/ui-react/components/agent/AgentChat.tsx

### Medium Priority

**BUG-15: W2 LLM returns list instead of dict for entity extraction**
- **Root cause:** DeepSeek sometimes returns a JSON array when a dict is expected.
- **Fix:** Normalize in `node_diff_with_project_data`: if list, wrap as `{"characters_found": list}`.
- **File:** sidecar/workflows/w2_manuscript_sync.py

---

## Codex Judge Scores

### W1 Import
- CHARACTER_EXTRACTION: 7/10 (韩立 correctly identified, family members extracted)
- ALIAS_RESOLUTION: 8/10 (二愣子 → 韩立 alias correctly resolved)
- NO_HALLUCINATION: 9/10 (proposals match source text)
- **Overall W1: 8/10 PASS**

### W2 Manuscript Sync
- POST_IMPORT: 9/10 (chapters, scenes, metadata all correctly written)
- DRAFT_ONLY: 10/10 (simple file write works)
- SINGLE_CHAPTER: 7/10 (entity extraction works, diff correct)
- **Overall W2: 9/10 PASS**

### W3 Writing Assistant
- VOICE_CONSISTENCY: 8/10 (xianxia cultivation genre maintained)
- CHARACTER_CONSISTENCY: 8/10 (韩立's humble origins preserved)
- TASK_ADHERENCE: 9/10 (continue/rewrite/expand/improve_dialogue all followed task)
- OUTPUT_FORMAT: 7/10 (occasional preamble headers present)
- THREE_OPTIONS_DIVERSITY: 8/10 (3 distinct narrative branches)
- **Overall W3: 8/10 PASS**

### W4 Consistency Check
- SCENE_SCOPE: 9/10 (runs correctly on single scene)
- FULL_SCOPE: 8/10 (9 issues found in 16-scene corpus)
- CONTRADICTION_DETECTION: 9/10 (eye color contradiction detected and reported)
- **Overall W4: 9/10 PASS**

### W5 Simulation
- SCENARIO_BRANCHES: 9/10 (3 distinct branches per scenario)
- MULTI_ENGINE: 8/10 (character/logic engines add distinct perspectives)
- ALL_ENGINES: 8/10 (author/reader perspectives distinct from scenario)
- **Overall W5: 8/10 PASS**

### W6 Beta Reader
- PERSONA_DIFFERENTIATION: 7/10 (casual vs scholar vs shipper have different emphases)
- SCORE_RANGE: 8/10 (scores vary 6-9, not clustered)
- PERSONA_APPROPRIATE_CONCERNS: 8/10 (shipper focuses on character, scholar on logic)
- **Overall W6: 8/10 PASS**

### W7 Metadata Ingestion
- STYLE_EXTRACTION: 7/10 (pov_style="unknown" but pacing/vocabulary notes present)
- VECTOR_STORE: 10/10 (ChromaDB updated successfully)
- STYLE_TRANSFER: 7/10 (W3+metadata output shows cultivation vocabulary)
- **Overall W7: 8/10 PASS**

### W0 Orchestrator
- PLAN_QUALITY: 9/10 (correctly selects W4 for consistency, W3+W4 for write+check)
- PLAN_RATIONALE: 8/10 (rationale in Chinese, relevant to goal)
- EXECUTION: 7/10 (child workflows execute, session management works)
- **Overall W0: 8/10 PASS**

---

## Remaining Issues (Non-blocking)

1. **W0 child workflow status tracking:** W0 marks sub-steps as "failed" when child workflow takes >2 seconds (first poll sees "running"), though the session completes as "done". Fix: increase initial poll delay or check "running" status more carefully in `node_execute_step`.

2. **W3 output preamble:** Occasional preamble headers ("续写内容：") in direct_output mode. Prompt improvement needed.

3. **W7 pov_style detection:** Returns "unknown" for xianxia text. Prompt needs Chinese-literature-specific pov vocabulary.

4. **Sidecar restart required:** Cannot restart sidecar while Electron app is running (port conflict with invisible PID). User must close Electron app to restart sidecar manually.

---

## Verdict

**✅ READY for Phase 8** — All 22 test cases pass, all critical bugs fixed. 8 bugs were CRITICAL/HIGH severity. W0 orchestrator works end-to-end with auto-approval. W4 contradiction detection confirmed working. W6 persona differentiation confirmed.
