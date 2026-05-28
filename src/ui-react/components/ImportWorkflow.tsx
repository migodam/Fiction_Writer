import React, { useCallback, useState } from 'react';
import { CheckCircle2, ClipboardCheck, Terminal } from 'lucide-react';
import { electronApi } from '../services/electronApi';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';
import { ImportConsole } from './ImportConsole';
import type { ImportObservabilitySummary, W1CustomProfileConfig, W1JudgeArtifactSummary, W1PromptProfile } from '../services/electronApi';

interface ImportWorkflowProps {
  onClose: () => void;
}

const profileExplanations: Record<W1PromptProfile, string> = {
  fast: 'Speed: fastest. Quality: draft scout. Window: broad 20-chapter batches. Validation: off. Expected cost: low.',
  balanced: 'Speed: moderate. Quality: named entities and chapter-level events. Window: 12 chapters. Validation: per-window. Expected cost: medium.',
  deep: 'Speed: slow. Quality: high coverage. Window: 8 chapters. Validation: per-window with supervisor/orchestrator enabled by default. Expected cost: high.',
  custom: 'Speed/cost follow your expert settings. Quality/window/validation are configurable. Supervisor/orchestrator are enabled by default.',
};

const formatChapterRange = (value: unknown) => {
  if (!value) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'object') {
    const range = value as { start?: string; end?: string };
    return [range.start, range.end].filter(Boolean).join(' - ');
  }
  return String(value);
};

const compactNumber = (value: number | undefined) => {
  if (typeof value !== 'number') return '';
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
  pass: 'text-green',
  acceptable_with_warnings: 'text-amber',
  warning: 'text-amber',
  fail: 'text-red',
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
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  </label>
);

const RuntimeField: React.FC<{ testId: string; label: string; value: React.ReactNode }> = ({ testId, label, value }) => {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div data-testid={testId} className="rounded-lg border border-border bg-card p-2">
      <div className="text-[10px] font-black uppercase tracking-widest text-text-3">{label}</div>
      <div className="mt-1 text-xs text-text">{value}</div>
    </div>
  );
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
  const w1ImportReviewReport = useProjectStore((s) => s.w1ImportReviewReport);
  const w1ActivityLog = useProjectStore((s) => s.w1ActivityLog);
  const w1IdleSeconds = useProjectStore((s) => s.w1IdleSeconds);
  const w1ElapsedSeconds = useProjectStore((s) => s.w1ElapsedSeconds);
  const w1ActiveApiCalls = useProjectStore((s) => s.w1ActiveApiCalls);
  const w1CancelRequested = useProjectStore((s) => s.w1CancelRequested);
  const w1ConnectionWarning = useProjectStore((s) => s.w1ConnectionWarning);
  const proposals = useProjectStore((s) => s.proposals);
  const resolveProposal = useProjectStore((s) => s.resolveProposal);
  const setW1ImportMode = useProjectStore((s) => s.setW1ImportMode);
  const setW1PromptProfile = useProjectStore((s) => s.setW1PromptProfile);
  const setW1CustomProfileConfig = useProjectStore((s) => s.setW1CustomProfileConfig);
  const startImport = useProjectStore((s) => s.startImport);
  const cancelImport = useProjectStore((s) => s.cancelImport);
  const { t } = useI18n();
  const [consoleOpen, setConsoleOpen] = useState(true);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const [acceptResult, setAcceptResult] = useState<{ accepted: number; remaining: number } | null>(null);

  const updateCustomProfile = useCallback((patch: Partial<W1CustomProfileConfig>) => {
    setW1CustomProfileConfig(patch);
  }, [setW1CustomProfileConfig]);

  const handlePickFile = useCallback(async () => {
    try {
      const files = await electronApi.pickFiles({
        filters: [{ name: 'Text Files', extensions: ['txt', 'md'] }],
      });
      if (files && files.length > 0) {
        startImport({ projectRoot: '', sourceFilePath: files[0] });
      }
    } catch {
      // user cancelled file dialog
    }
  }, [startImport]);

  const isIdle = w1Status === 'idle' || w1Status === 'error' || w1Status === 'cancelled';
  const safeAcceptIds = (w1ImportReviewReport?.safe_accept_ids || []).filter((id) =>
    proposals.some((proposal) => proposal.id === id),
  );
  const judgeSummary = (w1ImportReviewReport?.judge_artifact_summary ||
    w1ImportReviewReport?.judge_artifact ||
    w1RuntimeStatus?.judge_artifact_summary) as W1JudgeArtifactSummary | undefined;
  const hasRuntimeStatus = Boolean(w1RuntimeStatus && (
    w1RuntimeStatus.current_tool ||
    w1RuntimeStatus.current_window ||
    w1RuntimeStatus.chapter_range ||
    w1RuntimeStatus.orchestrator_phase ||
    typeof w1RuntimeStatus.judge_score === 'number' ||
    w1RuntimeStatus.rerun_reason ||
    w1RuntimeStatus.converge_status
  ));
  const latestActivity = w1ActivityLog[w1ActivityLog.length - 1];
  const activityMessage = latestActivity?.message || w1RuntimeStatus?.last_activity_message || t('import.activityStarting', 'Starting import… waiting for first activity event.');
  const isActivityIdle = w1IdleSeconds >= 90;
  const isBudgetExhausted = w1Errors.some((err) => /budget_exhausted|402|insufficient balance/i.test(err)) || w1RuntimeStatus?.converge_status === 'budget_exhausted';
  const acceptSafeAll = useCallback(() => {
    for (const proposalId of safeAcceptIds) {
      resolveProposal(proposalId, 'accepted');
    }
    setAcceptResult({ accepted: safeAcceptIds.length, remaining: proposals.length - safeAcceptIds.length });
  }, [resolveProposal, safeAcceptIds, proposals.length]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl custom-scrollbar">
        <h2 className="mb-4 text-lg font-semibold text-text">{t('import.title')}</h2>

        {/* Mode selector — visible when idle */}
        {isIdle && (
          <div className="mb-4 space-y-2">
            <p className="text-sm font-medium text-text-2">{t('import.mode')}</p>
            <label
              data-testid="w1-mode-content-only"
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 hover:bg-hover"
            >
              <input
                type="radio"
                name="importMode"
                value="import_content_only"
                checked={w1ImportMode === 'import_content_only'}
                onChange={() => setW1ImportMode('import_content_only')}
                className="mt-0.5 accent-brand"
              />
              <span>
                <span className="block text-sm font-medium text-text">{t('import.contentOnly')}</span>
                <span className="block text-xs text-text-3">
                  {t('import.contentOnlyDesc')}
                </span>
              </span>
            </label>
            <label
              data-testid="w1-mode-import-all"
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 hover:bg-hover"
            >
              <input
                type="radio"
                name="importMode"
                value="import_all"
                checked={w1ImportMode === 'import_all'}
                onChange={() => setW1ImportMode('import_all')}
                className="mt-0.5 accent-brand"
              />
              <span>
                <span className="block text-sm font-medium text-text">{t('import.importAll')}</span>
                <span className="block text-xs text-text-3">
                  {t('import.importAllDesc')}
                </span>
              </span>
            </label>
          </div>
        )}

        {isIdle && (
          <div className="mb-4 rounded-xl border border-border bg-bg-elev-1 p-3">
            <label htmlFor="w1-prompt-profile" className="mb-2 block text-sm font-medium text-text-2">
              {t('import.promptProfile')}
            </label>
            <select
              id="w1-prompt-profile"
              data-testid="w1-prompt-profile-select"
              value={w1PromptProfile}
              onChange={(event) => setW1PromptProfile(event.target.value as W1PromptProfile)}
              className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-text"
            >
              <option value="fast">{t('import.promptFast')}</option>
              <option value="balanced">{t('import.promptBalanced')}</option>
              <option value="deep">{t('import.promptDeep')}</option>
              <option value="custom">{t('import.promptCustom')}</option>
            </select>
            <p data-testid="w1-profile-explanation" className="mt-2 rounded-lg border border-border bg-card p-2 text-xs leading-relaxed text-text-2">
              {profileExplanations[w1PromptProfile]}
            </p>
            <p className="mt-2 text-xs text-text-3">{t('import.promptProfileDesc')}</p>
            {w1PromptProfile === 'custom' && (
              <div data-testid="w1-custom-expert-panel" className="mt-3 rounded-xl border border-brand/30 bg-brand/5 p-3">
                <div className="mb-3">
                  <div className="text-sm font-semibold text-text">{t('import.customExpert', 'Custom expert mode')}</div>
                  <p className="mt-1 text-xs text-text-3">
                    {t('import.customExpertDesc', 'Defaults mirror the planned custom backend profile: 2-6 chapter windows, scene-level event density, full topology, and three reruns.')}
                  </p>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <CustomSelect
                    id="w1-custom-quality-target"
                    label={t('import.qualityTarget', 'Quality target')}
                    value={w1CustomProfileConfig.quality_target}
                    onChange={(value) => updateCustomProfile({ quality_target: value as W1CustomProfileConfig['quality_target'] })}
                    options={[
                      { value: 'draft', label: 'Draft' },
                      { value: 'standard', label: 'Standard' },
                      { value: 'high', label: 'High' },
                      { value: 'max', label: 'Max' },
                    ]}
                  />
                  <label className="space-y-1 text-xs text-text-2">
                    <span className="font-semibold">{t('import.maxChaptersPerWindow', 'Max chapters per window')}</span>
                    <input
                      data-testid="w1-custom-max-chapters-per-window"
                      type="number"
                      min={1}
                      max={50}
                      value={w1CustomProfileConfig.chapters_per_window_max}
                      onChange={(event) => {
                        const next = Math.max(1, Number(event.target.value) || 1);
                        updateCustomProfile({ chapters_per_window_max: next, max_chapters_per_window: next });
                      }}
                      className="w-full rounded-lg border border-border bg-card px-2 py-1.5 text-xs text-text"
                    />
                  </label>
                  <CustomSelect
                    id="w1-custom-character-granularity"
                    label={t('import.characterGranularity', 'Character granularity')}
                    value={w1CustomProfileConfig.character_granularity}
                    onChange={(value) => updateCustomProfile({ character_granularity: value as W1CustomProfileConfig['character_granularity'] })}
                    options={[
                      { value: 'major_only', label: 'Major only' },
                      { value: 'named_only', label: 'Named only' },
                      { value: 'all', label: 'All named/role-bearing' },
                    ]}
                  />
                  <CustomSelect
                    id="w1-custom-event-density"
                    label={t('import.eventDensity', 'Event density')}
                    value={w1CustomProfileConfig.event_density}
                    onChange={(value) => updateCustomProfile({ event_density: value as W1CustomProfileConfig['event_density'] })}
                    options={[
                      { value: 'arc_level', label: 'Arc level' },
                      { value: 'chapter_level', label: 'Chapter level' },
                      { value: 'scene_level', label: 'Scene level' },
                    ]}
                  />
                  <CustomSelect
                    id="w1-custom-timeline-topology-depth"
                    label={t('import.timelineTopologyDepth', 'Timeline topology depth')}
                    value={w1CustomProfileConfig.timeline_topology_depth}
                    onChange={(value) => updateCustomProfile({ timeline_topology_depth: value as W1CustomProfileConfig['timeline_topology_depth'] })}
                    options={[
                      { value: 'flat', label: 'Flat' },
                      { value: 'branched', label: 'Branched' },
                      { value: 'full_dag', label: 'Full DAG' },
                    ]}
                  />
                  <CustomSelect
                    id="w1-custom-world-strictness"
                    label={t('import.worldStrictness', 'World strictness')}
                    value={w1CustomProfileConfig.world_strictness}
                    onChange={(value) => updateCustomProfile({ world_strictness: value as W1CustomProfileConfig['world_strictness'] })}
                    options={[
                      { value: 'named_only', label: 'Named only' },
                      { value: 'with_description', label: 'With description' },
                      { value: 'full_attributes', label: 'Full attributes' },
                    ]}
                  />
                  <CustomSelect
                    id="w1-custom-validation-strictness"
                    label={t('import.validationStrictness', 'Validation strictness')}
                    value={w1CustomProfileConfig.validation_strictness}
                    onChange={(value) => updateCustomProfile({ validation_strictness: value as W1CustomProfileConfig['validation_strictness'] })}
                    options={[
                      { value: 'off', label: 'Off' },
                      { value: 'per_window', label: 'Per window' },
                      { value: 'per_arc', label: 'Per arc' },
                    ]}
                  />
                  <label className="space-y-1 text-xs text-text-2">
                    <span className="font-semibold">{t('import.rerunBudget', 'Rerun budget')}</span>
                    <input
                      data-testid="w1-custom-rerun-budget"
                      type="number"
                      min={0}
                      max={6}
                      value={w1CustomProfileConfig.rerun_budget}
                      onChange={(event) => {
                        const next = Math.max(0, Number(event.target.value) || 0);
                        updateCustomProfile({ rerun_budget: next, max_rerun_iterations: next });
                      }}
                      className="w-full rounded-lg border border-border bg-card px-2 py-1.5 text-xs text-text"
                    />
                  </label>
                  <CustomSelect
                    id="w1-custom-language-policy"
                    label={t('import.languagePolicy', 'Language policy')}
                    value={w1CustomProfileConfig.language_policy}
                    onChange={(value) => updateCustomProfile({ language_policy: value as W1CustomProfileConfig['language_policy'] })}
                    options={[
                      { value: 'preserve_source', label: 'Preserve source' },
                      { value: 'normalize_to_source', label: 'Normalize to source' },
                      { value: 'allow_mixed', label: 'Allow mixed' },
                    ]}
                  />
                </div>
              </div>
            )}
            <details data-testid="w1-prompt-review-panel" className="mt-3 rounded-lg border border-border bg-card p-3 text-xs text-text-2">
              <summary className="cursor-pointer font-semibold text-text">{t('import.promptReview')}</summary>
              <ul className="mt-2 space-y-1">
                <li>{t('import.promptReviewScout')}</li>
                <li>{t('import.promptReviewReducer')}</li>
                <li>{t('import.promptReviewTimeline')}</li>
                <li>{t('import.promptReviewCache')}</li>
              </ul>
            </details>
          </div>
        )}

        {/* File picker — visible when idle */}
        {isIdle && (
          <button
            data-testid="w1-file-picker-btn"
            onClick={handlePickFile}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand/90"
          >
            {t('import.selectFile')}
          </button>
        )}

        {/* Progress — visible when running or paused */}
        {(w1Status === 'running' || w1Status === 'paused') && (
          <div className="space-y-3">
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
                  ? `${w1CompletedChunks} / ${w1TotalChunks} ${t('import.chunksProcessed')}`
                  : `${Math.round(w1Progress * 100)}%`}
              </span>
              {w1CurrentStep && (
                <span data-testid="w1-current-step" className="text-xs text-text-3">
                  {t('import.currentStep')}: {w1CurrentStep.replace(/_/g, ' ')}
                </span>
              )}
            </div>
            <div
              data-testid="w1-current-activity-card"
              className={`rounded-xl border p-3 text-xs ${
                isBudgetExhausted || w1CancelRequested
                  ? 'border-red/40 bg-red/10'
                  : isActivityIdle || w1ConnectionWarning
                    ? 'border-amber/40 bg-amber/10'
                    : 'border-border bg-bg-elev-1'
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-text-3">
                    {t('import.currentActivity', 'Current AI Activity')}
                  </div>
                  <div data-testid="w1-current-activity-message" className="mt-1 text-sm font-semibold text-text">
                    {activityMessage}
                  </div>
                  {latestActivity?.error && (
                    <div data-testid="w1-current-activity-error" className="mt-1 text-red">
                      {latestActivity.error}
                    </div>
                  )}
                  {w1ConnectionWarning && (
                    <div data-testid="w1-connection-warning" className="mt-1 text-amber">
                      {w1ConnectionWarning}
                    </div>
                  )}
                  {isActivityIdle && !w1ConnectionWarning && (
                    <div data-testid="w1-idle-warning" className="mt-1 text-amber">
                      {t('import.idleWarning', 'No new AI activity for a while. The model may be waiting on network or a long response.')}
                    </div>
                  )}
                </div>
                <div className="grid min-w-[220px] grid-cols-2 gap-2 text-[10px] text-text-2">
                  <RuntimeField testId="w1-activity-phase" label={t('import.activityPhase', 'Phase')} value={latestActivity?.phase || w1RuntimeStatus?.orchestrator_phase || w1CurrentStep} />
                  <RuntimeField testId="w1-activity-tool" label={t('import.currentTool', 'Tool')} value={latestActivity?.tool || w1RuntimeStatus?.current_tool} />
                  <RuntimeField testId="w1-activity-window" label={t('import.currentWindow', 'Window')} value={latestActivity?.window_id || w1RuntimeStatus?.current_window} />
                  <RuntimeField testId="w1-activity-prompt" label={t('import.prompt', 'Prompt')} value={latestActivity?.prompt_label} />
                  <RuntimeField testId="w1-activity-api-calls" label={t('import.activeApiCalls', 'API calls')} value={String(w1ActiveApiCalls)} />
                  <RuntimeField testId="w1-activity-elapsed" label={t('import.elapsed', 'Elapsed')} value={formatDuration(w1ElapsedSeconds)} />
                  <RuntimeField testId="w1-activity-idle" label={t('import.idle', 'Idle')} value={formatDuration(w1IdleSeconds)} />
                  <RuntimeField testId="w1-activity-profile" label={t('import.profile', 'Profile')} value={`${w1PromptProfile} / ${w1ImportMode}`} />
                </div>
              </div>
              {w1CancelRequested && (
                <div data-testid="w1-cancel-requested" className="mt-2 rounded bg-red/10 px-2 py-1 text-red">
                  {t('import.cancelRequested', 'Cancel requested. Stopping before new model calls.')}
                </div>
              )}
            </div>
            {hasRuntimeStatus && w1RuntimeStatus && (
              <div data-testid="w1-runtime-status-card" className="grid gap-2 rounded-xl border border-border bg-bg-elev-1 p-3 md:grid-cols-3">
                <RuntimeField testId="w1-status-current-tool" label={t('import.currentTool', 'Tool')} value={w1RuntimeStatus.current_tool} />
                <RuntimeField testId="w1-status-current-window" label={t('import.currentWindow', 'Window')} value={w1RuntimeStatus.current_window} />
                <RuntimeField testId="w1-status-chapter-range" label={t('import.chapterRange', 'Chapters')} value={formatChapterRange(w1RuntimeStatus.chapter_range)} />
                <RuntimeField testId="w1-status-orchestrator-phase" label={t('import.orchestratorPhase', 'Orchestrator')} value={w1RuntimeStatus.orchestrator_phase} />
                <RuntimeField testId="w1-status-judge-score" label={t('import.judgeScore', 'Judge score')} value={compactNumber(w1RuntimeStatus.judge_score)} />
                <RuntimeField testId="w1-status-converge-status" label={t('import.convergeStatus', 'Converge')} value={w1RuntimeStatus.converge_status} />
                <RuntimeField testId="w1-status-rerun-reason" label={t('import.rerunReason', 'Rerun reason')} value={w1RuntimeStatus.rerun_reason} />
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
                {t('import.console', 'Console')}
              </button>
              <button
                data-testid="w1-cancel-btn"
                onClick={cancelImport}
                className="rounded-lg border border-border px-4 py-1.5 text-sm text-text-2 hover:bg-hover"
              >
                {t('import.cancel')}
              </button>
            </div>
          </div>
        )}
        <ImportConsole visible={consoleOpen && ['running', 'paused', 'done', 'error'].includes(w1Status)} />

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
        {w1Status === 'done' && (
          <div data-testid="w1-review-step" className="mt-4 rounded-xl border border-green/30 bg-green/10 p-4">
            <div className="flex items-start gap-3">
              <ClipboardCheck size={18} className="mt-0.5 text-green" />
              <div>
                <p data-testid="w1-success-msg" className="text-sm font-semibold text-green">
                  {t('import.complete')}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-text-2">
                  {t('import.reviewSummary', 'Review report ready. Inspect proposals, failed chunks, duplicates, and safe batch actions before accepting imported changes.')}
                </p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg border border-border bg-card p-2">
                <div className="font-black uppercase tracking-widest text-text-3">{t('import.reviewStatus', 'Status')}</div>
                <div
                data-testid="w1-review-status"
                className={`mt-1 ${REVIEW_STATUS_COLOR[w1ImportReviewReport?.status ?? 'pass'] ?? 'text-text'}`}
              >
                {w1ImportReviewReport?.status || 'pass'}
              </div>
              </div>
              <div className="rounded-lg border border-border bg-card p-2">
                <div className="font-black uppercase tracking-widest text-text-3">{t('import.reviewProposals', 'Proposals')}</div>
                <div data-testid="w1-review-proposal-count" className="mt-1 text-text">{w1ProposalCount || proposals.length}</div>
              </div>
              <div className="rounded-lg border border-border bg-card p-2">
                <div className="font-black uppercase tracking-widest text-text-3">{t('import.reviewSafe', 'Safe')}</div>
                <div data-testid="w1-review-safe-count" className="mt-1 text-text">{safeAcceptIds.length}</div>
              </div>
            </div>
            {Boolean(w1ImportReviewReport?.warnings?.length) && (
              <div data-testid="w1-review-warnings" className="mt-3">
                <ul className="space-y-1 text-xs text-amber">
                  {(showAllWarnings
                    ? w1ImportReviewReport!.warnings!
                    : w1ImportReviewReport!.warnings!.slice(0, 4)
                  ).map((warning, index) => <li key={index}>{warning}</li>)}
                </ul>
                {(w1ImportReviewReport!.warnings!.length ?? 0) > 4 && (
                  <button
                    type="button"
                    data-testid="w1-review-warnings-toggle"
                    onClick={() => setShowAllWarnings((v) => !v)}
                    className="mt-1 text-xs text-text-3 underline hover:text-text-2"
                  >
                    {showAllWarnings
                      ? 'Show less'
                      : `Show ${w1ImportReviewReport!.warnings!.length - 4} more…`}
                  </button>
                )}
              </div>
            )}
            {Boolean(w1ImportReviewReport?.failed_chunks?.length) && (
              <div data-testid="w1-review-failed-chunks" className="mt-3 rounded-lg border border-red/30 bg-red/10 p-2 text-xs text-red">
                {t('import.reviewFailedChunks', 'Failed chunks')}: {w1ImportReviewReport?.failed_chunks?.length}
              </div>
            )}
            {judgeSummary && (
              <div data-testid="w1-review-judge-summary" className="mt-3 rounded-lg border border-border bg-card p-3 text-xs text-text-2">
                <div className="font-black uppercase tracking-widest text-text-3">{t('import.judgeArtifact', 'Judge artifact')}</div>
                <div className="mt-2 grid gap-2 md:grid-cols-3">
                  <RuntimeField testId="w1-review-judge-score" label={t('import.judgeScore', 'Judge score')} value={compactNumber(judgeSummary.score ?? judgeSummary.judge_score)} />
                  <RuntimeField testId="w1-review-converge-status" label={t('import.convergeStatus', 'Converge')} value={judgeSummary.converge_status ?? judgeSummary.status} />
                  <RuntimeField testId="w1-review-rerun-reason" label={t('import.rerunReason', 'Rerun reason')} value={judgeSummary.rerun_reason} />
                </div>
                {judgeSummary.summary && <p className="mt-2 leading-relaxed">{judgeSummary.summary}</p>}
                {Boolean(judgeSummary.required_reruns?.length) && (
                  <p className="mt-2 text-amber">{t('import.requiredReruns', 'Required reruns')}: {judgeSummary.required_reruns?.join(', ')}</p>
                )}
              </div>
            )}
            {(() => {
              const obs: ImportObservabilitySummary | undefined = w1ImportReviewReport?.import_observability;
              if (!obs) return null;
              const obsFields: Array<[string, number | boolean | undefined]> = [
                [t('import.obsCharacters', 'Characters'), obs.characters_extracted],
                [t('import.obsEvents', 'Events'), obs.events_extracted],
                [t('import.obsWorld', 'World items'), obs.world_items_extracted],
                [t('import.obsRelationships', 'Relationships'), obs.relationships_extracted],
                [t('import.obsChapters', 'Chapters written'), obs.manuscript_chapters_count],
                [t('import.obsBranches', 'Branches'), obs.branch_count],
                [t('import.obsDuplicates', 'Duplicates merged'), obs.duplicate_count],
              ];
              return (
                <div data-testid="w1-import-observability" className="mt-3 grid grid-cols-2 gap-1 rounded-xl border border-border bg-bg-elev-1 p-3 sm:grid-cols-4">
                  {obsFields.map(([label, value]) => value !== undefined && (
                    <div key={label} className="flex flex-col gap-0.5 text-[10px]">
                      <span className="font-black uppercase tracking-widest text-text-3">{label}</span>
                      <span className="text-sm font-semibold text-text">{String(value)}</span>
                    </div>
                  ))}
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
                {t('import.acceptSafeAll', 'Accept safe all')} ({safeAcceptIds.length})
              </button>
              <button
                type="button"
                data-testid="w1-review-open-console-btn"
                onClick={() => setConsoleOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[11px] font-black uppercase tracking-widest text-text-2 hover:bg-hover"
              >
                <Terminal size={12} />
                {t('import.console', 'Console')}
              </button>
            </div>
            {acceptResult && (
              <p data-testid="w1-accept-result" className="mt-2 text-xs text-text-2">
                {t('import.acceptResult', `${acceptResult.accepted} accepted. ${acceptResult.remaining} proposals require manual review.`)}
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
            {t('import.close')}
          </button>
        </div>
      </div>
    </div>
  );
};
