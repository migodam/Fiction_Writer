import React from 'react';
import { X } from 'lucide-react';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

interface ChapterPreviewModalProps {
  chapterId: string;
  onClose: () => void;
}

const statusColors: Record<string, string> = {
  draft: 'bg-yellow-500/20 text-yellow-400',
  revised: 'bg-blue-500/20 text-blue-400',
  final: 'bg-green-500/20 text-green-400',
};

export const ChapterPreviewModal = ({ chapterId, onClose }: ChapterPreviewModalProps) => {
  const { t } = useI18n();
  const chapters = useProjectStore((state) => state.chapters);
  const scenes = useProjectStore((state) => state.scenes);

  const chapter = chapters.find((c) => c.id === chapterId) || null;
  const chapterScenes = chapter
    ? scenes.filter((s) => chapter.sceneIds.includes(s.id)).sort((a, b) => a.orderIndex - b.orderIndex)
    : [];

  const totalWords = chapterScenes.reduce((sum, scene) => {
    if (scene.content) {
      const text = scene.content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
      return sum + (text ? text.split(' ').length : 0);
    }
    return sum;
  }, 0);

  const readingMinutes = Math.max(1, Math.round(totalWords / 200));
  const sceneCount = chapterScenes.length;

  const getSceneSummary = (content: string, summary: string) => {
    if (summary) return summary.slice(0, 200);
    const text = content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    return text.slice(0, 200);
  };

  const getSceneWordCount = (scene: { content: string }) => {
    const text = scene.content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    return text ? text.split(' ').length : 0;
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      data-testid="chapter-preview-modal"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-hidden rounded-[32px] border border-border bg-card shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-7 py-5">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('chapterPreview.title')}</div>
            <div className="text-lg font-black text-text">{chapter?.title || '—'}</div>
          </div>
          <div className="flex items-center gap-3">
            {chapter && (
              <span className={cn('rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em]', statusColors[chapter.status] || statusColors.draft)}>
                {chapter.status}
              </span>
            )}
            <button
              type="button"
              data-testid="chapter-preview-close-btn"
              className="rounded-xl border border-border p-2 text-text-2 hover:border-brand hover:text-text"
              onClick={onClose}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Stats bar */}
        <div
          className="flex items-center gap-6 border-b border-border bg-bg-elev-1 px-7 py-4"
          data-testid="chapter-preview-stats"
        >
          <div className="text-center">
            <div className="text-sm font-black text-text">{totalWords.toLocaleString()}</div>
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t('chapterPreview.wordCount', '{count} words').replace('{count}', '')}
            </div>
          </div>
          <div className="h-8 w-px bg-border" />
          <div className="text-center">
            <div className="text-sm font-black text-text">{readingMinutes}</div>
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t('chapterPreview.readingTime', '~{min} min read').replace('~', '').replace('{min}', '').trim()}
            </div>
          </div>
          <div className="h-8 w-px bg-border" />
          <div className="text-center">
            <div className="text-sm font-black text-text">{sceneCount}</div>
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t('chapterPreview.sceneCount', '{count} scenes').replace('{count}', '').trim()}
            </div>
          </div>
        </div>

        {/* Scene list */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-3">
          {chapterScenes.length === 0 ? (
            <div className="py-8 text-center text-sm text-text-3">{t('chapterPreview.noScenes')}</div>
          ) : (
            chapterScenes.map((scene) => (
              <div
                key={scene.id}
                data-testid={`chapter-preview-scene-${scene.id}`}
                className="rounded-2xl border border-border bg-bg-elev-1 p-4"
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div className="text-sm font-black text-text truncate">{scene.title}</div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.15em]', statusColors[scene.status] || statusColors.draft)}>
                      {scene.status}
                    </span>
                    <span className="text-[10px] font-black text-text-3">
                      {getSceneWordCount(scene)} {t('chapterPreview.wordCount', '{count} words').replace('{count}', '').trim()}
                    </span>
                  </div>
                </div>
                {(scene.summary || scene.content) && (
                  <div className="text-xs text-text-3 line-clamp-3 leading-relaxed">
                    {getSceneSummary(scene.content, scene.summary)}
                    {(scene.summary?.length || 0) > 200 || scene.content?.replace(/<[^>]*>/g, '').trim().length > 200 ? '…' : ''}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-border bg-bg-elev-2 px-7 py-4 flex justify-end">
          <button
            type="button"
            data-testid="chapter-preview-close-btn-footer"
            className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white"
            onClick={onClose}
          >
            {t('chapterPreview.close')}
          </button>
        </div>
      </div>
    </div>
  );
};
