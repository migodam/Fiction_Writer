import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ClipboardCheck, Terminal } from "lucide-react";
import { electronApi } from "../services/electronApi";
import { useProjectStore } from "../store";
import { useI18n } from "../i18n";
import { ImportConsole } from "./ImportConsole";
import { RecoveryCenter } from "./import-runtime/RecoveryCenter";
import { CheckpointTimeline } from "./import-runtime/CheckpointTimeline";
import { AgentDag } from "./import-runtime/AgentDag";
import type {
  ImportObservabilitySummary,
  W1CustomProfileConfig,
  W1JudgeArtifactSummary,
  W1PromptProfile,
} from "../services/electronApi";
import {
  createW1ExecutionStream,
  latestW1ExecutionEvent,
} from "../services/w1ExecutionStream";

interface ImportWorkflowProps {
  onClose: () => void;
}

const profileExplanations: Record<W1PromptProfile, string> = {
  fast: "Speed: fastest. Quality: draft scout. Window: broad 20-chapter batches. Validation: off. Expected cost: low.",
  balanced:
    "Speed: moderate. Quality: named entities and chapter-level events. Window: 12 chapters. Validation: per-window. Expected cost: medium.",
  deep: "Speed: slow. Quality: high coverage. Window: 8 chapters. Validation: per-window with supervisor/orchestrator enabled by default. Expected cost: high.",
  custom:
    "Speed/cost follow your expert settings. Quality/window/validation are configurable. Supervisor/orchestrator are enabled by default.",
};

type ImportPresetKey =
  | "auto"
  | "sparse_turning_points"
  | "chapter_level"
  | "scene_level"
  | "character_rich"
  | "relationship_light"
  | "manuscript_focused"
  | "advanced";

interface ImportPreset {
  key: ImportPresetKey;
  label: string;
  description: string;
  importMode: "import_content_only" | "import_all";
  profile: W1PromptProfile;
  configOverrides: Partial<W1CustomProfileConfig>;
}

const IMPORT_PRESETS: ImportPreset[] = [
  {
    key: "auto",
    label: "Auto (Orchestrator decides)",
    description:
      "Recommended. Orchestrator selects the best granularity for your source.",
    importMode: "import_all",
    profile: "balanced",
    configOverrides: {},
  },
  {
    key: "sparse_turning_points",
    label: "Sparse turning points",
    description: "Major plot turns only. Fast, low cost.",
    importMode: "import_all",
    profile: "custom",
    configOverrides: {
      event_density: "arc_level",
      character_granularity: "major_only",
      world_strictness: "named_only",
      timeline_topology_depth: "flat",
      validation_strictness: "off",
    },
  },
  {
    key: "chapter_level",
    label: "Chapter-level",
    description: "One entry per chapter. Balanced cost and quality.",
    importMode: "import_all",
    profile: "custom",
    configOverrides: {
      event_density: "chapter_level",
      character_granularity: "named_only",
      world_strictness: "with_description",
      timeline_topology_depth: "branched",
      validation_strictness: "per_window",
    },
  },
  {
    key: "scene_level",
    label: "Scene-level",
    description: "Scene-by-scene. High coverage, higher cost.",
    importMode: "import_all",
    profile: "custom",
    configOverrides: {
      event_density: "scene_level",
      character_granularity: "all",
      world_strictness: "full_attributes",
      timeline_topology_depth: "full_dag",
      validation_strictness: "per_window",
    },
  },
  {
    key: "character_rich",
    label: "Character-rich",
    description:
      "All characters with full detail. Good for character-heavy stories.",
    importMode: "import_all",
    profile: "custom",
    configOverrides: {
      character_granularity: "all",
      event_density: "scene_level",
      world_strictness: "full_attributes",
      timeline_topology_depth: "full_dag",
      validation_strictness: "per_arc",
    },
  },
  {
    key: "relationship_light",
    label: "Relationship-light",
    description: "Characters and events only; skips deep relationship mapping.",
    importMode: "import_all",
    profile: "custom",
    configOverrides: {
      event_density: "chapter_level",
      character_granularity: "named_only",
      world_strictness: "with_description",
      extract_relationships: false,
    },
  },
  {
    key: "manuscript_focused",
    label: "Manuscript-focused",
    description:
      "Imports chapter text only. No characters, events, or world model.",
    importMode: "import_content_only",
    profile: "fast",
    configOverrides: {},
  },
  {
    key: "advanced",
    label: "Advanced (custom)",
    description: "Configure every knob manually.",
    importMode: "import_all",
    profile: "custom",
    configOverrides: {},
  },
];

const formatChapterRange = (value: unknown) => {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    const range = value as { start?: string; end?: string };
    return [range.start, range.end].filter(Boolean).join(" - ");
  }
  return String(value);
};

const compactNumber = (value: number | undefined) => {
  if (typeof value !== "number") return "";
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
};

const formatDuration = (seconds: number | undefined) => {
  const total = Math.max(0, Math.floor(seconds ?? 0));
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  if (minutes <= 0) return `${remainder}s`;
  return `${minutes}m ${remainder}s`;
};

const REVIEW_STATUS_COLOR: Record<string, string> = {
  pass: "text-green",
  acceptable_with_warnings: "text-amber",
  warning: "text-amber",
  fail: "text-red",
};

const CustomSelect: React.FC<{
  id: string;
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}> = ({ id, label, value, options, onChange }) => (
  <label className="space-y-1 text-xs text-text-2">
    <span className="font-semibold">{label}</span>
    <select
      data-testid={id}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-lg border border-border bg-card px-2 py-1.5 text-xs text-text"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  </label>
);

const RuntimeField: React.FC<{
  testId: string;
  label: string;
  value: React.ReactNode;
}> = ({ testId, label, value }) => {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-border bg-card p-2"
    >
      <div className="text-[10px] font-black uppercase tracking-widest text-text-3">
        {label}
      </div>
      <div className="mt-1 text-xs text-text">{value}</div>
    </div>
  );
};

const formatTokens = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
};

const IMPORT_STAGES = [
  "segment",
  "pack",
  "extract",
  "reconcile",
  "architect",
  "review",
  "propose",
] as const;

const importStageFor = (step: string) => {
  const normalized = step.toLowerCase();
  if (/split|segment|manifest/.test(normalized)) return "segment";
  if (/pack|window/.test(normalized)) return "pack";
  if (/extract|process_chunks|scout/.test(normalized)) return "extract";
  if (/reconcile|reduc/.test(normalized)) return "reconcile";
  if (/architect|timeline/.test(normalized)) return "architect";
  if (/review|judge|converge/.test(normalized)) return "review";
  if (/write|proposal|done/.test(normalized)) return "propose";
  return "segment";
};

export const ImportWorkflow: React.FC<ImportWorkflowProps> = ({ onClose }) => {
  const w1Status = useProjectStore((s) => s.w1Status);
  const w1Progress = useProjectStore((s) => s.w1Progress);
  const w1CompletedChunks = useProjectStore((s) => s.w1CompletedChunks);
  const w1TotalChunks = useProjectStore((s) => s.w1TotalChunks);
  const w1Errors = useProjectStore((s) => s.w1Errors);
  const w1CurrentStep = useProjectStore((s) => s.w1CurrentStep);
  const w1ImportMode = useProjectStore((s) => s.w1ImportMode);
  const w1PromptProfile = useProjectStore((s) => s.w1PromptProfile);
  const w1CustomProfileConfig = useProjectStore((s) => s.w1CustomProfileConfig);
  const w1RuntimeStatus = useProjectStore((s) => s.w1RuntimeStatus);
  const w1ProposalCount = useProjectStore((s) => s.w1ProposalCount);
  const w1ExtractionCounts = useProjectStore((s) => s.w1ExtractionCounts);
  const w1ImportReviewReport = useProjectStore((s) => s.w1ImportReviewReport);
  const w1ConsoleLog = useProjectStore((s) => s.w1ConsoleLog);
  const w1ActivityLog = useProjectStore((s) => s.w1ActivityLog);
  const w1IdleSeconds = useProjectStore((s) => s.w1IdleSeconds);
  const w1ElapsedSeconds = useProjectStore((s) => s.w1ElapsedSeconds);
  const w1ActiveApiCalls = useProjectStore((s) => s.w1ActiveApiCalls);
  const w1TokenLedger = useProjectStore((s) => s.w1TokenLedger);
  const w1CancelRequested = useProjectStore((s) => s.w1CancelRequested);
  const w1ConnectionWarning = useProjectStore((s) => s.w1ConnectionWarning);
  const projectRoot = useProjectStore((s) => s.projectRoot);
  const proposals = useProjectStore((s) => s.proposals);
  const resolveProposals = useProjectStore((s) => s.resolveProposals);
  const setW1ImportMode = useProjectStore((s) => s.setW1ImportMode);
  const setW1PromptProfile = useProjectStore((s) => s.setW1PromptProfile);
  const setW1CustomProfileConfig = useProjectStore(
    (s) => s.setW1CustomProfileConfig,
  );
  const startImport = useProjectStore((s) => s.startImport);
  const cancelImport = useProjectStore((s) => s.cancelImport);
  const resetImport = useProjectStore((s) => s.resetImport);
  const w1RecoverableRuns = useProjectStore((s) => s.w1RecoverableRuns);
  const w1RuntimeEvents = useProjectStore((s) => s.w1RuntimeEvents);
  const w1RuntimeCheckpoints = useProjectStore((s) => s.w1RuntimeCheckpoints);
  const w1RuntimeLoading = useProjectStore((s) => s.w1RuntimeLoading);
  const w1RuntimeError = useProjectStore((s) => s.w1RuntimeError);
  const w1RuntimeGapWarning = useProjectStore((s) => s.w1RuntimeGapWarning);
  const w1RuntimeAction = useProjectStore((s) => s.w1RuntimeAction);
  const w1RuntimeSelectedAgent = useProjectStore((s) => s.w1RuntimeSelectedAgent);
  const w1RuntimeLineageId = useProjectStore((s) => s.w1RuntimeLineageId);
  const discoverW1Recovery = useProjectStore((s) => s.discoverW1Recovery);
  const syncW1Runtime = useProjectStore((s) => s.syncW1Runtime);
  const resumeW1Recovery = useProjectStore((s) => s.resumeW1Recovery);
  const forkW1Checkpoint = useProjectStore((s) => s.forkW1Checkpoint);
  const pauseW1Runtime = useProjectStore((s) => s.pauseW1Runtime);
  const cancelW1Runtime = useProjectStore((s) => s.cancelW1Runtime);
  const setW1RuntimeSelectedAgent = useProjectStore((s) => s.setW1RuntimeSelectedAgent);
  const { t } = useI18n();
  const [consoleOpen, setConsoleOpen] = useState(true);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const [acceptResult, setAcceptResult] = useState<{
    accepted: number;
    remaining: number;
  } | null>(null);
  const [sourceFilePath, setSourceFilePath] = useState("");

  useEffect(() => {
    void discoverW1Recovery();
    const interval = window.setInterval(() => void syncW1Runtime(), 4000);
    return () => window.clearInterval(interval);
  }, [discoverW1Recovery, syncW1Runtime, projectRoot]);

  const updateCustomProfile = useCallback(
    (patch: Partial<W1CustomProfileConfig>) => {
      setW1CustomProfileConfig(patch);
    },
    [setW1CustomProfileConfig],
  );

  const [activePreset, setActivePreset] = useState<ImportPresetKey>("auto");

  const applyPreset = useCallback(
    (preset: ImportPreset) => {
      setActivePreset(preset.key);
      setW1PromptProfile(preset.profile);
      setW1ImportMode(preset.importMode);
      if (Object.keys(preset.configOverrides).length > 0) {
        setW1CustomProfileConfig(preset.configOverrides);
      }
    },
    [setW1PromptProfile, setW1ImportMode, setW1CustomProfileConfig],
  );

  const handleExtractionToggle = useCallback(
    (patch: Partial<W1CustomProfileConfig>) => {
      if (activePreset !== "advanced") {
        setActivePreset("advanced");
        setW1PromptProfile("custom");
      }
      setW1CustomProfileConfig(patch);
    },
    [activePreset, setW1CustomProfileConfig, setW1PromptProfile],
  );

  const handlePickFile = useCallback(async () => {
    try {
      const files = await electronApi.pickFiles({
        filters: [{ name: "Text Files", extensions: ["txt", "md"] }],
      });
      if (files && files.length > 0) {
        setSourceFilePath(files[0]);
        void startImport({ projectRoot, sourceFilePath: files[0] });
      }
    } catch {
      // user cancelled file dialog
    }
  }, [projectRoot, startImport]);

  const isIdle =
    w1Status === "idle" || w1Status === "error" || w1Status === "cancelled";
  const safeAcceptIds = (w1ImportReviewReport?.safe_accept_ids || []).filter(
    (id) => proposals.some((proposal) => proposal.id === id),
  );
  const judgeSummary = (w1ImportReviewReport?.judge_artifact_summary ||
    w1ImportReviewReport?.judge_artifact ||
    w1RuntimeStatus?.judge_artifact_summary) as
    | W1JudgeArtifactSummary
    | undefined;
  const hasRuntimeStatus = Boolean(
    w1RuntimeStatus &&
    (w1RuntimeStatus.current_tool ||
      w1RuntimeStatus.current_window ||
      w1RuntimeStatus.chapter_range ||
      w1RuntimeStatus.orchestrator_phase ||
      typeof w1RuntimeStatus.judge_score === "number" ||
      w1RuntimeStatus.rerun_reason ||
      w1RuntimeStatus.converge_status),
  );
  const executionStream = createW1ExecutionStream(w1ActivityLog, w1ConsoleLog);
  const latestExecutionEvent = latestW1ExecutionEvent(executionStream);
  const latestActivity =
    latestExecutionEvent?.kind === "activity"
      ? latestExecutionEvent.activity
      : undefined;
  const activityMessage =
    latestActivity?.message ||
    w1RuntimeStatus?.last_activity_message ||
    t(
      "import.activityStarting",
      "Starting import... waiting for first activity event.",
    );
  const isActivityIdle = w1IdleSeconds >= 90;
  const isBudgetExhausted =
    w1Errors.some((err) =>
      /budget_exhausted|402|insufficient balance/i.test(err),
    ) || w1RuntimeStatus?.converge_status === "budget_exhausted";
  const activeStage = importStageFor(
    w1RuntimeStatus?.orchestrator_phase || w1CurrentStep || w1Status,
  );
  const acceptSafeAll = useCallback(() => {
    resolveProposals(safeAcceptIds, "accepted");
    setAcceptResult({
      accepted: safeAcceptIds.length,
      remaining: proposals.length - safeAcceptIds.length,
    });
  }, [resolveProposals, safeAcceptIds, proposals.length]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl custom-scrollbar">
        <h2 className="mb-4 text-lg font-semibold text-text">
          {t("import.title")}
        </h2>
        <RecoveryCenter runs={w1RecoverableRuns} loading={w1RuntimeLoading} error={w1RuntimeError} action={w1RuntimeAction} activeLineageId={w1RuntimeLineageId} onRefresh={() => void discoverW1Recovery()} onResume={(run) => void resumeW1Recovery(run)} onPause={() => void pauseW1Runtime()} onCancel={() => void cancelW1Runtime()} t={t} />
        {w1RuntimeGapWarning && <div className="mb-3 border-l-2 border-amber bg-amber/10 px-3 py-2 text-xs text-text-2" data-testid="w1-runtime-gap-warning">{t("import.runtimeGap", "Some runtime events were unavailable; the activity view resumes from the latest confirmed sequence.")}</div>}
        <CheckpointTimeline checkpoints={w1RuntimeCheckpoints} action={w1RuntimeAction} onFork={(checkpointId) => void forkW1Checkpoint(checkpointId)} t={t} />
        <AgentDag events={w1RuntimeEvents} selectedAgent={w1RuntimeSelectedAgent} onSelect={setW1RuntimeSelectedAgent} t={t} />
        <div
          data-testid="w1-import-entry"
          className="mb-4 grid gap-2 rounded-xl border border-border bg-bg-elev-1 p-3 text-xs sm:grid-cols-4"
        >
          <RuntimeField
            testId="w1-import-file"
            label={t("import.file", "File")}
            value={
              sourceFilePath ||
              t("import.chooseManuscript", "Choose a manuscript")
            }
          />
          <RuntimeField
            testId="w1-import-model"
            label={t("import.model", "Model")}
            value={w1PromptProfile}
          />
          <RuntimeField
            testId="w1-import-stage"
            label={t("import.stage", "Stage")}
            value={w1CurrentStep || w1Status}
          />
          <RuntimeField
            testId="w1-import-budget"
            label={t("import.budget", "Budget")}
            value={
              w1TokenLedger
                ? `${formatTokens(w1TokenLedger.actual_total_tokens ?? 0)} ${t("import.tokens", "tokens")}`
                : t("import.awaitingUsage", "Awaiting usage")
            }
          />
        </div>

        {/* Preset picker + extraction toggles — visible when idle */}
        {isIdle && (
          <div className="mb-4 grid gap-3 lg:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-medium text-text-2">
                {t("import.mode")}
              </p>
              <div
                data-testid="import-preset-list"
                className="grid grid-cols-2 gap-2"
              >
                {IMPORT_PRESETS.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    data-testid={`preset-${preset.key}`}
                    onClick={() => applyPreset(preset)}
                    className={`min-h-[76px] w-full rounded-lg border p-2 text-left transition-colors hover:bg-hover ${
                      activePreset === preset.key
                        ? "border-brand bg-brand/5"
                        : "border-border"
                    }`}
                  >
                    <span className="block text-xs font-medium text-text">
                      {t(`import.preset.${preset.key}`, preset.label)}
                    </span>
                    <span className="mt-1 block text-[10px] leading-snug text-text-3">
                      {t(`import.preset.${preset.key}Desc`, preset.description)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-3 rounded-lg border border-border bg-bg-elev-1 p-3">
              <div
                data-testid="w1-idle-extraction-summary"
                className="grid grid-cols-2 gap-2 text-xs text-text-2"
              >
                <RuntimeField
                  testId="w1-idle-profile"
                  label={t("import.profile", "Profile")}
                  value={w1PromptProfile}
                />
                <RuntimeField
                  testId="w1-idle-scope"
                  label={t("import.scope", "Scope")}
                  value={
                    w1ImportMode === "import_content_only"
                      ? t("import.manuscriptOnly", "Manuscript only")
                      : t("import.fullExtraction", "Full extraction")
                  }
                />
              </div>
              {activePreset !== "manuscript_focused" && (
                <div className="rounded-xl border border-border bg-bg-elev-1 p-3">
                  <p className="mb-2 text-xs font-semibold text-text-2">
                    {t("import.extractionToggles", "Extract")}
                  </p>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <label className="flex items-center gap-2 text-xs text-text-2">
                      <input
                        type="checkbox"
                        checked
                        disabled
                        className="accent-brand"
                      />
                      {t("import.extractManuscript", "Manuscript")}
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-xs text-text-2">
                      <input
                        type="checkbox"
                        data-testid="toggle-extract-relationships"
                        checked={
                          w1CustomProfileConfig.extract_relationships !== false
                        }
                        onChange={(e) =>
                          handleExtractionToggle({
                            extract_relationships: e.target.checked,
                          })
                        }
                        className="accent-brand"
                      />
                      {t("import.extractRelationships", "Relationships")}
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-xs text-text-2">
                      <input
                        type="checkbox"
                        data-testid="toggle-extract-world"
                        checked={w1CustomProfileConfig.extract_world !== false}
                        onChange={(e) =>
                          handleExtractionToggle({
                            extract_world: e.target.checked,
                          })
                        }
                        className="accent-brand"
                      />
                      {t("import.extractWorld", "World Model")}
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-xs text-text-2">
                      <input
                        type="checkbox"
                        data-testid="toggle-extract-timeline"
                        checked={
                          w1CustomProfileConfig.extract_timeline !== false
                        }
                        onChange={(e) =>
                          handleExtractionToggle({
                            extract_timeline: e.target.checked,
                          })
                        }
                        className="accent-brand"
                      />
                      {t("import.extractTimeline", "Timeline")}
                    </label>
                  </div>
                </div>
              )}
              {activePreset === "advanced" && (
                <div
                  data-testid="w1-custom-expert-panel"
                  className="rounded-xl border border-brand/30 bg-brand/5 p-3"
                >
                  <div className="mb-3">
                    <div className="text-sm font-semibold text-text">
                      {t("import.customExpert", "Custom expert mode")}
                    </div>
                    <p className="mt-1 text-xs text-text-3">
                      {t(
                        "import.customExpertDesc",
                        "Defaults mirror the planned custom backend profile: 2-6 chapter windows, scene-level event density, full topology, and three reruns.",
                      )}
                    </p>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <CustomSelect
                      id="w1-custom-quality-target"
                      label={t("import.qualityTarget", "Quality target")}
                      value={w1CustomProfileConfig.quality_target}
                      onChange={(value) =>
                        updateCustomProfile({
                          quality_target:
                            value as W1CustomProfileConfig["quality_target"],
                        })
                      }
                      options={[
                        { value: "draft", label: "Draft" },
                        { value: "standard", label: "Standard" },
                        { value: "high", label: "High" },
                        { value: "max", label: "Max" },
                      ]}
                    />
                    <label className="space-y-1 text-xs text-text-2">
                      <span className="font-semibold">
                        {t(
                          "import.maxChaptersPerWindow",
                          "Max chapters per window",
                        )}
                      </span>
                      <input
                        data-testid="w1-custom-max-chapters-per-window"
                        type="number"
                        min={1}
                        max={50}
                        value={w1CustomProfileConfig.chapters_per_window_max}
                        onChange={(event) => {
                          const next = Math.max(
                            1,
                            Number(event.target.value) || 1,
                          );
                          updateCustomProfile({
                            chapters_per_window_max: next,
                            max_chapters_per_window: next,
                          });
                        }}
                        className="w-full rounded-lg border border-border bg-card px-2 py-1.5 text-xs text-text"
                      />
                    </label>
                    <CustomSelect
                      id="w1-custom-character-granularity"
                      label={t(
                        "import.characterGranularity",
                        "Character granularity",
                      )}
                      value={w1CustomProfileConfig.character_granularity}
                      onChange={(value) =>
                        updateCustomProfile({
                          character_granularity:
                            value as W1CustomProfileConfig["character_granularity"],
                        })
                      }
                      options={[
                        { value: "major_only", label: "Major only" },
                        { value: "named_only", label: "Named only" },
                        { value: "all", label: "All named/role-bearing" },
                      ]}
                    />
                    <CustomSelect
                      id="w1-custom-event-density"
                      label={t("import.eventDensity", "Event density")}
                      value={w1CustomProfileConfig.event_density}
                      onChange={(value) =>
                        updateCustomProfile({
                          event_density:
                            value as W1CustomProfileConfig["event_density"],
                        })
                      }
                      options={[
                        { value: "arc_level", label: "Arc level" },
                        { value: "chapter_level", label: "Chapter level" },
                        { value: "scene_level", label: "Scene level" },
                      ]}
                    />
                    <CustomSelect
                      id="w1-custom-timeline-topology-depth"
                      label={t(
                        "import.timelineTopologyDepth",
                        "Timeline topology depth",
                      )}
                      value={w1CustomProfileConfig.timeline_topology_depth}
                      onChange={(value) =>
                        updateCustomProfile({
                          timeline_topology_depth:
                            value as W1CustomProfileConfig["timeline_topology_depth"],
                        })
                      }
                      options={[
                        { value: "flat", label: "Flat" },
                        { value: "branched", label: "Branched" },
                        { value: "full_dag", label: "Full DAG" },
                      ]}
                    />
                    <CustomSelect
                      id="w1-custom-world-strictness"
                      label={t("import.worldStrictness", "World strictness")}
                      value={w1CustomProfileConfig.world_strictness}
                      onChange={(value) =>
                        updateCustomProfile({
                          world_strictness:
                            value as W1CustomProfileConfig["world_strictness"],
                        })
                      }
                      options={[
                        { value: "named_only", label: "Named only" },
                        {
                          value: "with_description",
                          label: "With description",
                        },
                        { value: "full_attributes", label: "Full attributes" },
                      ]}
                    />
                    <CustomSelect
                      id="w1-custom-validation-strictness"
                      label={t(
                        "import.validationStrictness",
                        "Validation strictness",
                      )}
                      value={w1CustomProfileConfig.validation_strictness}
                      onChange={(value) =>
                        updateCustomProfile({
                          validation_strictness:
                            value as W1CustomProfileConfig["validation_strictness"],
                        })
                      }
                      options={[
                        { value: "off", label: "Off" },
                        { value: "per_window", label: "Per window" },
                        { value: "per_arc", label: "Per arc" },
                      ]}
                    />
                    <label className="space-y-1 text-xs text-text-2">
                      <span className="font-semibold">
                        {t("import.rerunBudget", "Rerun budget")}
                      </span>
                      <input
                        data-testid="w1-custom-rerun-budget"
                        type="number"
                        min={0}
                        max={6}
                        value={w1CustomProfileConfig.rerun_budget}
                        onChange={(event) => {
                          const next = Math.max(
                            0,
                            Number(event.target.value) || 0,
                          );
                          updateCustomProfile({
                            rerun_budget: next,
                            max_rerun_iterations: next,
                          });
                        }}
                        className="w-full rounded-lg border border-border bg-card px-2 py-1.5 text-xs text-text"
                      />
                    </label>
                    <CustomSelect
                      id="w1-custom-language-policy"
                      label={t("import.languagePolicy", "Language policy")}
                      value={w1CustomProfileConfig.language_policy}
                      onChange={(value) =>
                        updateCustomProfile({
                          language_policy:
                            value as W1CustomProfileConfig["language_policy"],
                        })
                      }
                      options={[
                        { value: "preserve_source", label: "Preserve source" },
                        {
                          value: "normalize_to_source",
                          label: "Normalize to source",
                        },
                        { value: "allow_mixed", label: "Allow mixed" },
                      ]}
                    />
                  </div>
                </div>
              )}
              <details
                data-testid="w1-prompt-review-panel"
                className="mt-3 rounded-lg border border-border bg-card p-3 text-xs text-text-2"
              >
                <summary className="cursor-pointer font-semibold text-text">
                  {t("import.promptReview")}
                </summary>
                <ul className="mt-2 space-y-1">
                  <li>{t("import.promptReviewScout")}</li>
                  <li>{t("import.promptReviewReducer")}</li>
                  <li>{t("import.promptReviewTimeline")}</li>
                  <li>{t("import.promptReviewCache")}</li>
                </ul>
              </details>
              <button
                data-testid="w1-file-picker-btn"
                onClick={handlePickFile}
                className="w-full rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand/90"
              >
                {t("import.selectFile")}
              </button>
            </div>
          </div>
        )}

        {/* Progress — visible when running or paused */}
        {(w1Status === "running" || w1Status === "paused") && (
          <div className="space-y-3">
            <div
              data-testid="w1-stage-rail"
              className="grid grid-cols-4 gap-1 sm:grid-cols-7"
            >
              {IMPORT_STAGES.map((stage) => {
                const isCurrent = stage === activeStage;
                const isComplete =
                  IMPORT_STAGES.indexOf(stage) <
                  IMPORT_STAGES.indexOf(activeStage);
                return (
                  <div
                    key={stage}
                    data-testid={`w1-stage-${stage}`}
                    className={`rounded border px-1.5 py-1 text-center text-[10px] font-semibold capitalize ${isCurrent ? "border-brand bg-brand/10 text-brand" : isComplete ? "border-green/30 bg-green/10 text-green" : "border-border text-text-3"}`}
                  >
                    {t(`import.stage.${stage}`, stage)}
                  </div>
                );
              })}
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-bg-elev-1">
              <div
                data-testid="w1-progress-bar"
                className="h-full rounded-full bg-brand transition-all duration-300"
                style={{ width: `${w1Progress * 100}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-sm text-text-2">
              <span>
                {w1TotalChunks > 0
                  ? `${w1CompletedChunks} / ${w1TotalChunks} ${t("import.chunksProcessed")}`
                  : `${Math.round(w1Progress * 100)}%`}
              </span>
              {w1CurrentStep && (
                <span
                  data-testid="w1-current-step"
                  className="text-xs text-text-3"
                >
                  {t("import.currentStep")}: {w1CurrentStep.replace(/_/g, " ")}
                </span>
              )}
            </div>
            {w1ExtractionCounts && (
              <div
                data-testid="w1-extraction-counts"
                className="grid gap-2 rounded-xl border border-border bg-bg-elev-1 p-3 text-xs text-text-2 sm:grid-cols-4"
              >
                <RuntimeField
                  testId="w1-extraction-counts-characters"
                  label={t("import.obsCharacters", "Characters")}
                  value={String(w1ExtractionCounts.characters)}
                />
                <RuntimeField
                  testId="w1-extraction-counts-events"
                  label={t("import.obsEvents", "Events")}
                  value={String(w1ExtractionCounts.events)}
                />
                <RuntimeField
                  testId="w1-extraction-counts-world"
                  label={t("import.obsWorld", "World items")}
                  value={String(w1ExtractionCounts.world_items)}
                />
                <RuntimeField
                  testId="w1-extraction-counts-relationships"
                  label={t("import.obsRelationships", "Relationships")}
                  value={String(w1ExtractionCounts.relationships)}
                />
              </div>
            )}
            <div
              data-testid="w1-run-summary"
              className="grid grid-cols-3 gap-2 rounded-lg border border-border bg-card p-2"
            >
              <RuntimeField
                testId="w1-summary-api"
                label={t("import.apiCalls", "API calls")}
                value={String(
                  w1TokenLedger?.api_call_count ?? w1ActiveApiCalls,
                )}
              />
              <RuntimeField
                testId="w1-summary-tokens"
                label={t("import.tokens", "Tokens")}
                value={
                  w1TokenLedger
                    ? formatTokens(
                        w1TokenLedger.actual_total_tokens ||
                          w1TokenLedger.estimated_input_tokens,
                      )
                    : t("import.awaitingUsage", "Awaiting usage")
                }
              />
              <RuntimeField
                testId="w1-summary-elapsed"
                label={t("import.elapsed", "Elapsed")}
                value={formatDuration(w1ElapsedSeconds)}
              />
            </div>
            {isBudgetExhausted && (
              <div
                data-testid="w1-budget-exhausted-banner"
                className="rounded-xl border border-red/40 bg-red/10 p-3 text-xs font-semibold text-red"
              >
                {t(
                  "import.budgetExhausted",
                  "402 / Budget exhausted — import stopped. Check your provider balance.",
                )}
              </div>
            )}
            <div
              data-testid="w1-current-activity-card"
              className={`rounded-xl border p-3 text-xs ${
                isBudgetExhausted || w1CancelRequested
                  ? "border-red/40 bg-red/10"
                  : isActivityIdle || w1ConnectionWarning
                    ? "border-amber/40 bg-amber/10"
                    : "border-border bg-bg-elev-1"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-text-3">
                    {t("import.currentActivity", "Current AI Activity")}
                  </div>
                  <div
                    data-testid="w1-current-activity-message"
                    className="mt-1 text-sm font-semibold text-text"
                  >
                    {activityMessage}
                  </div>
                  {latestActivity?.error && (
                    <div
                      data-testid="w1-current-activity-error"
                      className="mt-1 text-red"
                    >
                      {latestActivity.error}
                    </div>
                  )}
                  {w1ConnectionWarning && (
                    <div
                      data-testid="w1-connection-warning"
                      className="mt-1 text-amber"
                    >
                      {w1ConnectionWarning}
                    </div>
                  )}
                  {isActivityIdle && !w1ConnectionWarning && (
                    <div
                      data-testid="w1-idle-warning"
                      className="mt-1 text-amber"
                    >
                      {t(
                        "import.idleWarning",
                        "No new AI activity for a while. The model may be waiting on network or a long response.",
                      )}
                    </div>
                  )}
                </div>
                <div className="grid min-w-[220px] grid-cols-2 gap-2 text-[10px] text-text-2">
                  <RuntimeField
                    testId="w1-activity-phase"
                    label={t("import.activityPhase", "Phase")}
                    value={
                      latestActivity?.phase ||
                      w1RuntimeStatus?.orchestrator_phase ||
                      w1CurrentStep
                    }
                  />
                  <RuntimeField
                    testId="w1-activity-tool"
                    label={t("import.currentTool", "Tool")}
                    value={
                      latestActivity?.tool || w1RuntimeStatus?.current_tool
                    }
                  />
                  <RuntimeField
                    testId="w1-activity-window"
                    label={t("import.currentWindow", "Window")}
                    value={
                      latestActivity?.window_id ||
                      w1RuntimeStatus?.current_window
                    }
                  />
                  <RuntimeField
                    testId="w1-activity-prompt"
                    label={t("import.prompt", "Prompt")}
                    value={latestActivity?.prompt_label}
                  />
                  <RuntimeField
                    testId="w1-activity-api-calls"
                    label={t("import.activeApiCalls", "API calls")}
                    value={String(w1ActiveApiCalls)}
                  />
                  <RuntimeField
                    testId="w1-activity-elapsed"
                    label={t("import.elapsed", "Elapsed")}
                    value={formatDuration(w1ElapsedSeconds)}
                  />
                  <RuntimeField
                    testId="w1-activity-idle"
                    label={t("import.idle", "Idle")}
                    value={formatDuration(w1IdleSeconds)}
                  />
                  <RuntimeField
                    testId="w1-activity-profile"
                    label={t("import.profile", "Profile")}
                    value={`${w1PromptProfile} / ${w1ImportMode}`}
                  />
                </div>
              </div>
              {w1CancelRequested && (
                <div
                  data-testid="w1-cancel-requested"
                  className="mt-2 rounded bg-red/10 px-2 py-1 text-red"
                >
                  {t(
                    "import.cancelRequested",
                    "Cancel requested. Stopping before new model calls.",
                  )}
                </div>
              )}
            </div>
            {hasRuntimeStatus && w1RuntimeStatus && (
              <div
                data-testid="w1-runtime-status-card"
                className="grid gap-2 rounded-xl border border-border bg-bg-elev-1 p-3 md:grid-cols-3"
              >
                <RuntimeField
                  testId="w1-status-current-tool"
                  label={t("import.currentTool", "Tool")}
                  value={w1RuntimeStatus.current_tool}
                />
                <RuntimeField
                  testId="w1-status-current-window"
                  label={t("import.currentWindow", "Window")}
                  value={w1RuntimeStatus.current_window}
                />
                <RuntimeField
                  testId="w1-status-chapter-range"
                  label={t("import.chapterRange", "Chapters")}
                  value={formatChapterRange(w1RuntimeStatus.chapter_range)}
                />
                <RuntimeField
                  testId="w1-status-orchestrator-phase"
                  label={t("import.orchestratorPhase", "Orchestrator")}
                  value={w1RuntimeStatus.orchestrator_phase}
                />
                <RuntimeField
                  testId="w1-status-judge-score"
                  label={t("import.judgeScore", "Judge score")}
                  value={compactNumber(w1RuntimeStatus.judge_score)}
                />
                <RuntimeField
                  testId="w1-status-converge-status"
                  label={t("import.convergeStatus", "Converge")}
                  value={w1RuntimeStatus.converge_status}
                />
                <RuntimeField
                  testId="w1-status-rerun-reason"
                  label={t("import.rerunReason", "Rerun reason")}
                  value={w1RuntimeStatus.rerun_reason}
                />
              </div>
            )}
            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="w1-console-toggle-btn"
                onClick={() => setConsoleOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-text-2 hover:bg-hover"
              >
                <Terminal size={12} />
                {t("import.console", "Console")}
              </button>
              <button
                data-testid="w1-cancel-btn"
                onClick={cancelImport}
                className="rounded-lg border border-border px-4 py-1.5 text-sm text-text-2 hover:bg-hover"
              >
                {t("import.cancel")}
              </button>
            </div>
          </div>
        )}

        {(w1Status === "error" || w1Status === "cancelled") && (
          <div
            data-testid="w1-recovery-card"
            className="mt-4 rounded-xl border border-red/30 bg-red/10 p-3 text-sm text-text"
          >
            <p className="font-semibold">
              {w1Status === "cancelled"
                ? "Import cancelled"
                : "Import needs attention"}
            </p>
            {w1Errors.map((error, index) => (
              <p
                key={`${error}-${index}`}
                data-testid="w1-recovery-error-item"
                className="mt-1 text-xs text-red"
              >
                {error}
              </p>
            ))}
            <div className="mt-3 flex gap-2">
              {sourceFilePath && (
                <button
                  type="button"
                  data-testid="w1-retry-btn"
                  className="rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-white"
                  onClick={() =>
                    void startImport({ projectRoot, sourceFilePath })
                  }
                >
                  Retry import
                </button>
              )}
              <button
                type="button"
                data-testid="w1-reset-btn"
                className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold"
                onClick={resetImport}
              >
                Choose another file
              </button>
            </div>
          </div>
        )}
        {w1TokenLedger && (
          <div
            data-testid="w1-token-cost-card"
            className="mt-3 grid gap-2 rounded-xl border border-border bg-bg-elev-1 p-3 text-xs text-text-2 sm:grid-cols-4"
          >
            <RuntimeField
              testId="w1-token-cost-input"
              label={t("import.inputTokens", "Input tokens")}
              value={
                w1TokenLedger.actual_input_tokens > 0
                  ? formatTokens(w1TokenLedger.actual_input_tokens)
                  : `${formatTokens(w1TokenLedger.estimated_input_tokens)} (est.)`
              }
            />
            <RuntimeField
              testId="w1-token-cost-output"
              label={t("import.outputTokens", "Output tokens")}
              value={
                w1TokenLedger.actual_output_tokens > 0
                  ? formatTokens(w1TokenLedger.actual_output_tokens)
                  : undefined
              }
            />
            <RuntimeField
              testId="w1-token-cost-calls"
              label={t("import.apiCalls", "API calls")}
              value={String(w1TokenLedger.api_call_count)}
            />
            <RuntimeField
              testId="w1-token-cost-estimated-cost"
              label={t("import.estimatedCost", "Est. cost")}
              value={
                w1TokenLedger.cost_usd != null
                  ? `$${w1TokenLedger.cost_usd.toFixed(4)}`
                  : w1TokenLedger.cost_unavailable_reason
              }
            />
          </div>
        )}
        <ImportConsole
          visible={
            consoleOpen &&
            ["running", "paused", "done", "error"].includes(w1Status)
          }
        />

        {/* Errors */}
        {w1Errors.length > 0 && (
          <ul className="mt-4 space-y-1">
            {w1Errors.map((err, i) => (
              <li
                key={i}
                data-testid="w1-error-item"
                className="rounded bg-red/10 px-3 py-1.5 text-sm text-red"
              >
                {err}
              </li>
            ))}
          </ul>
        )}

        {/* Success */}
        {w1Status === "done" && (
          <div
            data-testid="w1-review-step"
            className="mt-4 rounded-xl border border-green/30 bg-green/10 p-4"
          >
            <div className="flex items-start gap-3">
              <ClipboardCheck size={18} className="mt-0.5 text-green" />
              <div>
                <p
                  data-testid="w1-success-msg"
                  className="text-sm font-semibold text-green"
                >
                  {t("import.complete")}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-text-2">
                  {t(
                    "import.reviewSummary",
                    "Review report ready. Inspect proposals, failed chunks, duplicates, and safe batch actions before accepting imported changes.",
                  )}
                </p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg border border-border bg-card p-2">
                <div className="font-black uppercase tracking-widest text-text-3">
                  {t("import.reviewStatus", "Status")}
                </div>
                <div
                  data-testid="w1-review-status"
                  className={`mt-1 ${REVIEW_STATUS_COLOR[w1ImportReviewReport?.status ?? "pass"] ?? "text-text"}`}
                >
                  {w1ImportReviewReport?.status || "pass"}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-card p-2">
                <div className="font-black uppercase tracking-widest text-text-3">
                  {t("import.reviewProposals", "Proposals")}
                </div>
                <div
                  data-testid="w1-review-proposal-count"
                  className="mt-1 text-text"
                >
                  {w1ProposalCount || proposals.length}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-card p-2">
                <div className="font-black uppercase tracking-widest text-text-3">
                  {t("import.reviewSafe", "Safe")}
                </div>
                <div
                  data-testid="w1-review-safe-count"
                  className="mt-1 text-text"
                >
                  {safeAcceptIds.length}
                </div>
              </div>
            </div>
            {Boolean(w1ImportReviewReport?.warnings?.length) && (
              <div data-testid="w1-review-warnings" className="mt-3">
                <ul className="space-y-1 text-xs text-amber">
                  {(showAllWarnings
                    ? w1ImportReviewReport!.warnings!
                    : w1ImportReviewReport!.warnings!.slice(0, 4)
                  ).map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
                {(w1ImportReviewReport!.warnings!.length ?? 0) > 4 && (
                  <button
                    type="button"
                    data-testid="w1-review-warnings-toggle"
                    onClick={() => setShowAllWarnings((v) => !v)}
                    className="mt-1 text-xs text-text-3 underline hover:text-text-2"
                  >
                    {showAllWarnings
                      ? "Show less"
                      : `Show ${w1ImportReviewReport!.warnings!.length - 4} more…`}
                  </button>
                )}
              </div>
            )}
            {Boolean(w1ImportReviewReport?.failed_chunks?.length) && (
              <div
                data-testid="w1-review-failed-chunks"
                className="mt-3 rounded-lg border border-red/30 bg-red/10 p-2 text-xs text-red"
              >
                {t("import.reviewFailedChunks", "Failed chunks")}:{" "}
                {w1ImportReviewReport?.failed_chunks?.length}
              </div>
            )}
            {judgeSummary && (
              <div
                data-testid="w1-review-judge-summary"
                className="mt-3 rounded-lg border border-border bg-card p-3 text-xs text-text-2"
              >
                <div className="font-black uppercase tracking-widest text-text-3">
                  {t("import.judgeArtifact", "Judge artifact")}
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-3">
                  <RuntimeField
                    testId="w1-review-judge-score"
                    label={t("import.judgeScore", "Judge score")}
                    value={compactNumber(
                      judgeSummary.score ?? judgeSummary.judge_score,
                    )}
                  />
                  <RuntimeField
                    testId="w1-review-converge-status"
                    label={t("import.convergeStatus", "Converge")}
                    value={judgeSummary.converge_status ?? judgeSummary.status}
                  />
                  <RuntimeField
                    testId="w1-review-rerun-reason"
                    label={t("import.rerunReason", "Rerun reason")}
                    value={judgeSummary.rerun_reason}
                  />
                </div>
                {judgeSummary.summary && (
                  <p className="mt-2 leading-relaxed">{judgeSummary.summary}</p>
                )}
                {Boolean(judgeSummary.required_reruns?.length) && (
                  <p className="mt-2 text-amber">
                    {t("import.requiredReruns", "Required reruns")}:{" "}
                    {judgeSummary.required_reruns?.join(", ")}
                  </p>
                )}
              </div>
            )}
            {(() => {
              const obs: ImportObservabilitySummary | undefined =
                w1ImportReviewReport?.import_observability;
              if (!obs) return null;
              const obsFields: Array<[string, number | boolean | undefined]> = [
                [
                  t("import.obsCharacters", "Characters"),
                  obs.characters_extracted,
                ],
                [t("import.obsEvents", "Events"), obs.events_extracted],
                [
                  t("import.obsWorld", "World items"),
                  obs.world_items_extracted,
                ],
                [
                  t("import.obsRelationships", "Relationships"),
                  obs.relationships_extracted,
                ],
                [
                  t("import.obsChapters", "Chapters written"),
                  obs.manuscript_chapters_count,
                ],
                [t("import.obsBranches", "Branches"), obs.branch_count],
                [
                  t("import.obsDuplicates", "Duplicates merged"),
                  obs.duplicate_count,
                ],
              ];
              return (
                <div
                  data-testid="w1-import-observability"
                  className="mt-3 grid grid-cols-2 gap-1 rounded-xl border border-border bg-bg-elev-1 p-3 sm:grid-cols-4"
                >
                  {obsFields.map(
                    ([label, value]) =>
                      value !== undefined && (
                        <div
                          key={label}
                          className="flex flex-col gap-0.5 text-[10px]"
                        >
                          <span className="font-black uppercase tracking-widest text-text-3">
                            {label}
                          </span>
                          <span className="text-sm font-semibold text-text">
                            {String(value)}
                          </span>
                        </div>
                      ),
                  )}
                </div>
              );
            })()}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                data-testid="w1-accept-safe-all-btn"
                disabled={safeAcceptIds.length === 0}
                onClick={acceptSafeAll}
                className="inline-flex items-center gap-1.5 rounded-lg bg-green px-3 py-1.5 text-[11px] font-black uppercase tracking-widest text-text-invert disabled:cursor-not-allowed disabled:opacity-50"
              >
                <CheckCircle2 size={12} />
                {t("import.acceptSafeAll", "Accept safe all")} (
                {safeAcceptIds.length})
              </button>
              <button
                type="button"
                data-testid="w1-review-open-console-btn"
                onClick={() => setConsoleOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[11px] font-black uppercase tracking-widest text-text-2 hover:bg-hover"
              >
                <Terminal size={12} />
                {t("import.console", "Console")}
              </button>
            </div>
            {acceptResult && (
              <p
                data-testid="w1-accept-result"
                className="mt-2 text-xs text-text-2"
              >
                {t(
                  "import.acceptResult",
                  `${acceptResult.accepted} accepted. ${acceptResult.remaining} proposals require manual review.`,
                )}
              </p>
            )}
          </div>
        )}

        {/* Close button — always visible */}
        <div className="mt-6 flex justify-end">
          <button
            data-testid="w1-close-btn"
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-1.5 text-sm text-text-2 hover:bg-hover"
          >
            {t("import.close")}
          </button>
        </div>
      </div>
    </div>
  );
};
