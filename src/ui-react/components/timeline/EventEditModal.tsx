import React, { useState } from 'react';
import { X } from 'lucide-react';
import { useProjectStore } from '../../store';
import { useI18n } from '../../i18n';
import type { TimelineEvent } from '../../models/project';

interface EventEditModalProps {
  event: TimelineEvent;
  onClose: () => void;
}

const importanceToNumber = (importance?: TimelineEvent['importance']): number => {
  if (importance === 'critical') return 5;
  if (importance === 'high') return 4;
  if (importance === 'medium') return 3;
  if (importance === 'low') return 2;
  return 1;
};

const numberToImportance = (n: number): TimelineEvent['importance'] => {
  if (n >= 5) return 'critical';
  if (n >= 4) return 'high';
  if (n >= 3) return 'medium';
  return 'low';
};

export function EventEditModal({ event, onClose }: EventEditModalProps) {
  const { updateTimelineEvent, deleteTimelineEvent } = useProjectStore();
  const { t } = useI18n();
  const [draft, setDraft] = useState<TimelineEvent>(event);
  const importanceNum = importanceToNumber(draft.importance);

  const handleSave = () => {
    updateTimelineEvent(draft);
    onClose();
  };

  const handleDelete = () => {
    deleteTimelineEvent(event.id);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-black/60 p-6" onClick={onClose}>
      <div
        className="w-full max-w-md overflow-hidden rounded-[32px] border border-border bg-bg-elev-1 shadow-2"
        onClick={(e) => e.stopPropagation()}
        data-testid="event-edit-modal"
      >
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-6 py-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
              {t('timeline.editEvent')}
            </div>
            <div className="mt-0.5 text-sm font-black text-text truncate max-w-[300px]">{event.title}</div>
          </div>
          <button
            type="button"
            data-testid="event-edit-close-btn"
            className="rounded p-2 text-text-3 hover:bg-hover hover:text-text"
            onClick={onClose}
          >
            <X size={15} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <div className="mb-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t('common.title')}
            </div>
            <input
              data-testid="event-edit-title"
              className="w-full rounded-2xl border border-border bg-bg px-4 py-2.5 text-sm text-text outline-none"
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </div>

          <div>
            <div className="mb-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t('timeline.timeText')}
            </div>
            <input
              data-testid="event-edit-time"
              className="w-full rounded-2xl border border-border bg-bg px-4 py-2.5 text-sm text-text outline-none"
              value={draft.time || ''}
              onChange={(e) => setDraft({ ...draft, time: e.target.value })}
              placeholder="e.g. Year 1, Day 3"
            />
          </div>

          <div>
            <div className="mb-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t('timeline.summary')}
            </div>
            <textarea
              data-testid="event-edit-summary"
              className="w-full rounded-2xl border border-border bg-bg px-4 py-2.5 text-sm text-text-2 outline-none h-24 resize-none"
              value={draft.summary}
              onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
            />
          </div>

          <div>
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t('timeline.importance')}: {importanceNum}/5
            </div>
            <input
              data-testid="event-edit-importance"
              type="range"
              min={1}
              max={5}
              step={1}
              value={importanceNum}
              onChange={(e) =>
                setDraft({ ...draft, importance: numberToImportance(Number(e.target.value)) })
              }
              className="w-full accent-brand"
            />
            <div className="flex justify-between text-[9px] text-text-3 mt-1">
              <span>Low</span>
              <span>Critical</span>
            </div>
          </div>
        </div>

        <div className="border-t border-border p-4 flex items-center gap-2">
          <button
            type="button"
            data-testid="event-edit-delete-btn"
            className="rounded-xl border border-red-500/40 px-4 py-2 text-xs font-black text-red-400 hover:bg-red-500/10"
            onClick={handleDelete}
          >
            {t('timeline.deleteEvent')}
          </button>
          <div className="flex-1" />
          <button
            type="button"
            data-testid="event-edit-save-btn"
            className="rounded-xl bg-brand px-5 py-2 text-xs font-black text-white"
            onClick={handleSave}
          >
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
