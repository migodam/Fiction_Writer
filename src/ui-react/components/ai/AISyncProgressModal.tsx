import React, { forwardRef, useImperativeHandle, useState } from 'react';
import { useI18n } from '../../i18n';

export interface AISyncProgressModalProps {
  totalItems: number;
  onCancel: () => void;
  onClose: () => void;
}

export interface AISyncProgressModalRef {
  setProgress: (current: number, statusText: string) => void;
  setComplete: () => void;
}

export const AISyncProgressModal = forwardRef<AISyncProgressModalRef, AISyncProgressModalProps>(
  ({ totalItems, onCancel, onClose }, ref) => {
    const { t } = useI18n();
    const [current, setCurrent] = useState(0);
    const [statusText, setStatusText] = useState('');
    const [complete, setCompleteState] = useState(false);

    useImperativeHandle(ref, () => ({
      setProgress(cur: number, text: string) {
        setCurrent(cur);
        setStatusText(text);
      },
      setComplete() {
        setCompleteState(true);
      },
    }));

    const percent = totalItems > 0 ? Math.min(100, (current / totalItems) * 100) : 0;

    const progressLabel = complete
      ? t('aiSync.complete')
      : t('aiSync.progress', '{current}/{total} items')
          .replace('{current}', String(current))
          .replace('{total}', String(totalItems));

    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
        data-testid="ai-sync-modal"
      >
        <div className="mx-4 w-full max-w-md rounded-[28px] border border-border bg-card p-6 shadow-2xl">
          <div className="mb-5 text-base font-black text-text">{t('aiSync.title')}</div>

          {/* Progress bar track */}
          <div className="mb-3 h-2 w-full overflow-hidden rounded-full bg-bg-elev-1">
            <div
              data-testid="ai-sync-progress-bar"
              className="h-full rounded-full bg-brand transition-all duration-300"
              style={{ width: `${percent}%` }}
            />
          </div>

          {/* Status text */}
          <div
            data-testid="ai-sync-status"
            className="mb-5 text-sm text-text-2"
          >
            {complete ? t('aiSync.complete') : statusText || progressLabel}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2">
            {!complete && (
              <button
                type="button"
                data-testid="ai-sync-cancel-btn"
                onClick={onCancel}
                className="rounded-xl border border-border px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-text-2 hover:border-brand"
              >
                {t('aiSync.cancel')}
              </button>
            )}
            {complete && (
              <button
                type="button"
                data-testid="ai-sync-close-btn"
                onClick={onClose}
                className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white hover:opacity-90"
              >
                {t('aiSync.close')}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }
);

AISyncProgressModal.displayName = 'AISyncProgressModal';
