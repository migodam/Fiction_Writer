import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, ChevronDown, FileText } from 'lucide-react';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

function stripHtml(content: string): string {
  if (content.includes('<')) {
    return content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  }
  return content;
}

function countWords(content: string): number {
  const text = stripHtml(content);
  if (!text) return 0;
  return text.split(/\s+/).filter(Boolean).length;
}

const statusColors: Record<string, string> = {
  draft: 'bg-gray-200 text-gray-700',
  revised: 'bg-yellow-200 text-yellow-800',
  final: 'bg-green-200 text-green-800',
};

export const ManuscriptNavigator = () => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { chapters, scenes, setSelectedEntity } = useProjectStore();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const sortedChapters = useMemo(
    () => [...chapters].sort((a, b) => a.orderIndex - b.orderIndex),
    [chapters]
  );

  const scenesByChapter = useMemo(() => {
    const map: Record<string, typeof scenes> = {};
    for (const chapter of sortedChapters) {
      const chapterScenes = scenes
        .filter((s) => chapter.sceneIds.includes(s.id))
        .sort((a, b) => a.orderIndex - b.orderIndex);
      map[chapter.id] = chapterScenes;
    }
    return map;
  }, [sortedChapters, scenes]);

  const chapterWordCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const chapter of sortedChapters) {
      counts[chapter.id] = (scenesByChapter[chapter.id] || []).reduce(
        (sum, scene) => sum + countWords(scene.content || ''),
        0
      );
    }
    return counts;
  }, [sortedChapters, scenesByChapter]);

  const allCollapsed = sortedChapters.length > 0 && sortedChapters.every((c) => collapsed[c.id]);

  const toggleCollapseAll = () => {
    if (allCollapsed) {
      setCollapsed({});
    } else {
      const next: Record<string, boolean> = {};
      for (const c of sortedChapters) next[c.id] = true;
      setCollapsed(next);
    }
  };

  const toggleChapter = (id: string) => {
    setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg" data-testid="manuscript-navigator">
      {/* Header */}
      <div className="border-b border-border bg-bg-elev-2 px-4 py-3 flex items-center justify-between">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
            {t('manuscript.title')}
          </div>
        </div>
        {sortedChapters.length > 0 && (
          <button
            type="button"
            data-testid="manuscript-collapse-all-btn"
            className="rounded-md border border-border px-2 py-1 text-[11px] text-text-2 hover:bg-hover"
            onClick={toggleCollapseAll}
          >
            {allCollapsed ? t('manuscript.expandAll') : t('manuscript.collapseAll')}
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {sortedChapters.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full px-6 py-12 text-center">
            <FileText size={32} className="text-text-2 mb-3 opacity-40" />
            <p className="text-[13px] text-text-2">{t('manuscript.empty')}</p>
          </div>
        ) : (
          sortedChapters.map((chapter) => {
            const isCollapsed = !!collapsed[chapter.id];
            const chapterScenes = scenesByChapter[chapter.id] || [];
            const wordCount = chapterWordCounts[chapter.id] || 0;
            return (
              <div key={chapter.id} className="border-b border-border last:border-b-0">
                {/* Chapter header */}
                <button
                  type="button"
                  data-testid={`manuscript-chapter-${chapter.id}`}
                  className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-hover"
                  onClick={() => toggleChapter(chapter.id)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {isCollapsed ? (
                      <ChevronRight size={14} className="shrink-0 text-text-2" />
                    ) : (
                      <ChevronDown size={14} className="shrink-0 text-text-2" />
                    )}
                    <span className="truncate text-[12px] font-semibold text-text">
                      {chapter.title}
                    </span>
                  </div>
                  <span className="ml-2 shrink-0 text-[10px] text-text-2">
                    {wordCount.toLocaleString()} {t('manuscript.wordCount')}
                  </span>
                </button>

                {/* Scenes list */}
                {!isCollapsed && (
                  <div className="pb-1">
                    {chapterScenes.map((scene) => {
                        const sceneWords = countWords(scene.content || '');
                        const statusClass =
                          statusColors[scene.status || 'draft'] || statusColors.draft;
                        return (
                          <button
                            key={scene.id}
                            type="button"
                            data-testid={`scene-item-${scene.id}`}
                            className={cn(
                              'flex w-full items-center justify-between px-10 py-2 text-left hover:bg-hover'
                            )}
                            onClick={() => {
                              setSelectedEntity('scene', scene.id);
                              navigate('/writing/scenes');
                            }}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="truncate text-[11px] text-text">
                                {scene.title}
                              </span>
                              <span
                                className={cn(
                                  'shrink-0 rounded px-1 py-0.5 text-[9px] font-medium uppercase',
                                  statusClass
                                )}
                              >
                                {t(`scene.status.${scene.status || 'draft'}`)}
                              </span>
                            </div>
                            <span className="ml-2 shrink-0 text-[10px] text-text-2">
                              {sceneWords.toLocaleString()} {t('manuscript.wordCount')}
                            </span>
                          </button>
                        );
                      })
                    }
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
