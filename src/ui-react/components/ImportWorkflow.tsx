import React, { useCallback } from 'react';
import { electronApi } from '../services/electronApi';
import { useProjectStore } from '../store';

interface ImportWorkflowProps {
  onClose: () => void;
}

export const ImportWorkflow: React.FC<ImportWorkflowProps> = ({ onClose }) => {
  const w1Status = useProjectStore((s) => s.w1Status);
  const w1Progress = useProjectStore((s) => s.w1Progress);
  const w1CompletedChunks = useProjectStore((s) => s.w1CompletedChunks);
  const w1TotalChunks = useProjectStore((s) => s.w1TotalChunks);
  const w1Errors = useProjectStore((s) => s.w1Errors);
  const w1ImportMode = useProjectStore((s) => s.w1ImportMode);
  const setW1ImportMode = useProjectStore((s) => s.setW1ImportMode);
  const startImport = useProjectStore((s) => s.startImport);
  const cancelImport = useProjectStore((s) => s.cancelImport);

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-text">Import Novel</h2>

        {/* Mode selector — visible when idle */}
        {isIdle && (
          <div className="mb-4 space-y-2">
            <p className="text-sm font-medium text-text-2">Import mode</p>
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
                <span className="block text-sm font-medium text-text">Import Content Only</span>
                <span className="block text-xs text-text-3">
                  Fast — splits novel into chapters and scenes, no AI extraction. ~5 seconds.
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
                <span className="block text-sm font-medium text-text">Import All</span>
                <span className="block text-xs text-text-3">
                  Full AI extraction — characters, relationships, world, timeline, settings.
                  10–60 min for a full novel.
                </span>
              </span>
            </label>
          </div>
        )}

        {/* File picker — visible when idle */}
        {isIdle && (
          <button
            data-testid="w1-file-picker-btn"
            onClick={handlePickFile}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand/90"
          >
            Select File
          </button>
        )}

        {/* Progress — visible when running */}
        {w1Status === 'running' && (
          <div className="space-y-3">
            <div className="h-3 w-full overflow-hidden rounded-full bg-bg-elev-1">
              <div
                data-testid="w1-progress-bar"
                className="h-full rounded-full bg-brand transition-all duration-300"
                style={{ width: `${w1Progress * 100}%` }}
              />
            </div>
            <p className="text-sm text-text-2">
              {w1CompletedChunks} / {w1TotalChunks} chunks processed
            </p>
            <button
              data-testid="w1-cancel-btn"
              onClick={cancelImport}
              className="rounded-lg border border-border px-4 py-1.5 text-sm text-text-2 hover:bg-hover"
            >
              Cancel
            </button>
          </div>
        )}

        {/* Errors */}
        {w1Errors.length > 0 && (
          <ul className="mt-4 space-y-1">
            {w1Errors.map((err, i) => (
              <li
                key={i}
                data-testid="w1-error-item"
                className="rounded bg-red-500/10 px-3 py-1.5 text-sm text-red-400"
              >
                {err}
              </li>
            ))}
          </ul>
        )}

        {/* Success */}
        {w1Status === 'done' && (
          <p data-testid="w1-success-msg" className="mt-4 text-sm text-green-400">
            Import complete.
          </p>
        )}

        {/* Close button — always visible */}
        <div className="mt-6 flex justify-end">
          <button
            data-testid="w1-close-btn"
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-1.5 text-sm text-text-2 hover:bg-hover"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
