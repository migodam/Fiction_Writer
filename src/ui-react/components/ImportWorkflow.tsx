import React, { useCallback, useState } from 'react';
import { CheckCircle2, ClipboardCheck, Terminal } from 'lucide-react';
import { electronApi } from '../services/electronApi';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';
import { ImportConsole } from './ImportConsole';

interface ImportWorkflowProps {
  onClose: () => void;
}

export const ImportWorkflow: React.FC<ImportWorkflowProps> = ({ onClose }) => {
  const w1Status = useProjectStore((s) => s.w1Status);
  const w1Progress = useProjectStore((s) => s.w1Progress);
  const w1CompletedChunks = useProjectStore((s) => s.w1CompletedChunks);
  const w1TotalChunks = useProjectStore((s) => s.w1TotalChunks);
  const w1Errors = useProjectStore((s) => s.w1Errors);
  const w1CurrentStep = useProjectStore((s) => s.w1CurrentStep);
  const w1ImportMode = useProjectStore((s) => s.w1ImportMode);
  const w1PromptProfile = useProjectStore((s) => s.w1PromptProfile);
  const w1ProposalCount = useProjectStore((s) => s.w1ProposalCount);
  const w1ImportReviewReport = useProjectStore((s) => s.w1ImportReviewReport);
  const proposals = useProjectStore((s) => s.proposals);
  const resolveProposal = useProjectStore((s) => s.resolveProposal);
  const setW1ImportMode = useProjectStore((s) => s.setW1ImportMode);
  const setW1PromptProfile = useProjectStore((s) => s.setW1PromptProfile);
  const startImport = useProjectStore((s) => s.startImport);
  const cancelImport = useProjectStore((s) => s.cancelImport);
  const { t } = useI18n();
  const [consoleOpen, setConsoleOpen] = useState(true);

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
  const acceptSafeAll = useCallback(() => {
    for (const proposalId of safeAcceptIds) {
      resolveProposal(proposalId, 'accepted');
    }
  }, [resolveProposal, safeAcceptIds]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-xl">
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
              onChange={(event) => setW1PromptProfile(event.target.value as 'fast' | 'balanced' | 'deep' | 'custom')}
              className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-text"
            >
              <option value="fast">{t('import.promptFast')}</option>
              <option value="balanced">{t('import.promptBalanced')}</option>
              <option value="deep">{t('import.promptDeep')}</option>
              <option value="custom">{t('import.promptCustom')}</option>
            </select>
            <p className="mt-2 text-xs text-text-3">{t('import.promptProfileDesc')}</p>
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
                <div data-testid="w1-review-status" className="mt-1 text-text">{w1ImportReviewReport?.status || 'pass'}</div>
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
              <ul data-testid="w1-review-warnings" className="mt-3 space-y-1 text-xs text-amber">
                {w1ImportReviewReport?.warnings?.slice(0, 4).map((warning, index) => <li key={index}>{warning}</li>)}
              </ul>
            )}
            {Boolean(w1ImportReviewReport?.failed_chunks?.length) && (
              <div data-testid="w1-review-failed-chunks" className="mt-3 rounded-lg border border-red/30 bg-red/10 p-2 text-xs text-red">
                {t('import.reviewFailedChunks', 'Failed chunks')}: {w1ImportReviewReport?.failed_chunks?.length}
              </div>
            )}
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
