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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-surface p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-text-1">Import Novel</h2>

        {/* File picker — visible when idle */}
        {(w1Status === 'idle' || w1Status === 'error' || w1Status === 'cancelled') && (
          <button
            data-testid="w1-file-picker-btn"
            onClick={handlePickFile}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90"
          >
            Select File
          </button>
        )}

        {/* Progress — visible when running */}
        {w1Status === 'running' && (
          <div className="space-y-3">
            <div className="h-3 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                data-testid="w1-progress-bar"
                className="h-full rounded-full bg-accent transition-all duration-300"
                style={{ width: `${w1Progress * 100}%` }}
              />
            </div>
            <p className="text-sm text-text-2">
              {w1CompletedChunks} / {w1TotalChunks} chunks processed
            </p>
            <button
              data-testid="w1-cancel-btn"
              onClick={cancelImport}
              className="rounded-lg border border-border px-4 py-1.5 text-sm text-text-2 hover:bg-surface-2"
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
            className="rounded-lg border border-border px-4 py-1.5 text-sm text-text-2 hover:bg-surface-2"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
