import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BookOpen, Box, ChevronLeft, ChevronRight, Clock, MoreVertical, PanelLeft, PanelRight, Plus, Search, Sparkles, Type, Users, Wand2, Zap } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { PaneResizeHandle } from './PaneResizeHandle';
import { cn } from '../utils';

export const WritingWorkspace = () => {
  const { chapters, scenes, characters, timelineEvents, worldItems, scripts, storyboards, selectedEntity, setSelectedEntity, updateScene, updateScript, addChapter, updateChapter, addScene, syncProjectUiState } = useProjectStore();
  const {
    sidebarSection,
    setLastActionStatus,
    writingOutlineWidth,
    writingContextWidth,
    isWritingOutlineCollapsed,
    isWritingContextCollapsed,
    toggleWritingPane,
    editorWidth,
    openContextMenu,
  } = useUIStore();
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const requestedScene = searchParams.get('scene');
  const requestedChapter = searchParams.get('chapter');
  const activeSceneId = selectedEntity.type === 'scene' ? selectedEntity.id : requestedScene || scenes[0]?.id;
  const activeScene = scenes.find((scene) => scene.id === activeSceneId) || scenes[0] || null;
  const activeChapterId = selectedEntity.type === 'chapter' ? selectedEntity.id : requestedChapter || activeScene?.chapterId || chapters[0]?.id || null;
  const activeChapter = chapters.find((chapter) => chapter.id === activeChapterId) || chapters[0] || null;
  const linkedItems = worldItems.filter((item) => activeScene?.linkedWorldItemIds.includes(item.id));
  const linkedCharacters = characters.filter((character) => activeScene?.linkedCharacterIds.includes(character.id));
  const linkedEvents = timelineEvents.filter((event) => activeScene?.linkedEventIds.includes(event.id));
  const contextCharacters = useMemo(
    () => mergeRecent(linkedCharacters, characters.slice().reverse(), 8),
    [characters, linkedCharacters],
  );
  const contextEvents = useMemo(
    () => mergeRecent(linkedEvents, timelineEvents.slice().reverse(), 8),
    [linkedEvents, timelineEvents],
  );
  const contextWorldItems = useMemo(
    () => mergeRecent(linkedItems, worldItems.slice().reverse(), 8),
    [linkedItems, worldItems],
  );
  const recentScenes = useMemo(() => scenes.slice().sort((a, b) => b.orderIndex - a.orderIndex).slice(0, 5), [scenes]);
  const [sceneQuery, setSceneQuery] = useState('');
  const [localContent, setLocalContent] = useState(activeScene?.content || '');
  const [localTitle, setLocalTitle] = useState(activeScene?.title || '');
  const [localChapterTitle, setLocalChapterTitle] = useState(activeChapter?.title || '');
  const [localChapterSummary, setLocalChapterSummary] = useState(activeChapter?.summary || '');
  const [localChapterGoal, setLocalChapterGoal] = useState(activeChapter?.goal || '');
  const [localChapterNotes, setLocalChapterNotes] = useState(activeChapter?.notes || '');
  const activeScriptId = selectedEntity.type === 'script' ? selectedEntity.id : scripts[0]?.id || null;
  const activeScript = scripts.find((script) => script.id === activeScriptId) || scripts[0] || null;
  const activeStoryboardId = selectedEntity.type === 'storyboard' ? selectedEntity.id : storyboards[0]?.id || null;
  const activeStoryboard = storyboards.find((storyboard) => storyboard.id === activeStoryboardId) || storyboards[0] || null;
  const [scriptQuery, setScriptQuery] = useState('');
  const [localScriptContent, setLocalScriptContent] = useState(activeScript?.content || '');
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (requestedScene) setSelectedEntity('scene', requestedScene);
  }, [requestedScene, setSelectedEntity]);

  useEffect(() => {
    if (!activeScene) return;
    setLocalContent(activeScene.content);
    setLocalTitle(activeScene.title);
  }, [activeScene?.id]);

  useEffect(() => {
    if (!activeChapter) return;
    setLocalChapterTitle(activeChapter.title);
    setLocalChapterSummary(activeChapter.summary);
    setLocalChapterGoal(activeChapter.goal);
    setLocalChapterNotes(activeChapter.notes);
  }, [activeChapter?.id]);

  useEffect(() => {
    if (!activeScript) return;
    setLocalScriptContent(activeScript.content);
  }, [activeScript?.id]);

  useEffect(() => {
    syncProjectUiState();
  }, [writingOutlineWidth, writingContextWidth, isWritingOutlineCollapsed, isWritingContextCollapsed, syncProjectUiState]);

  const persistScene = (nextScene: typeof activeScene) => {
    if (!nextScene) return;
    updateScene(nextScene);
    setLastActionStatus('Saved');
  };

  const persistChapter = () => {
    if (!activeChapter) return;
    updateChapter({
      ...activeChapter,
      title: localChapterTitle,
      summary: localChapterSummary,
      goal: localChapterGoal,
      notes: localChapterNotes,
    });
    setLastActionStatus('Saved');
  };

  const filteredChapters = chapters.map((chapter) => ({
    ...chapter,
    visibleScenes: scenes
      .filter((scene) => scene.chapterId === chapter.id)
      .filter((scene) => `${scene.title} ${scene.summary}`.toLowerCase().includes(sceneQuery.toLowerCase())),
  })).filter((chapter) => chapter.visibleScenes.length || !sceneQuery);

  if (sidebarSection === 'chapters') {
    return (
      <div className="flex h-full overflow-hidden bg-bg">
        <aside style={{ width: writingOutlineWidth }} className="flex h-full flex-col border-r border-border bg-bg-elev-1 shadow-1" data-testid="writing-chapters-sidebar">
          <div className="border-b border-border bg-bg-elev-2 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Chapters</div>
                <div className="text-sm font-black text-text">Structure Editor</div>
              </div>
              <button
                type="button"
                className="rounded-xl border border-border p-2 text-brand hover:border-brand"
                data-testid="add-chapter-btn"
                onClick={() => {
                  const nextChapterId = `chap_${Date.now()}`;
                  addChapter({
                    id: nextChapterId,
                    title: `Chapter ${chapters.length + 1}`,
                    summary: '',
                    goal: '',
                    notes: '',
                    sceneIds: [],
                    orderIndex: chapters.length,
                    status: 'draft',
                  });
                  setSelectedEntity('chapter', nextChapterId);
                }}
              >
                <Plus size={16} />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2">
            {chapters.map((chapter) => (
              <button
                key={chapter.id}
                type="button"
                className={cn('w-full rounded-2xl border px-4 py-3 text-left', activeChapter?.id === chapter.id ? 'border-brand bg-selected' : 'border-border bg-bg hover:border-brand')}
                onClick={() => setSelectedEntity('chapter', chapter.id)}
                data-testid={`chapter-item-${chapter.id}`}
              >
                <div className="text-sm font-black text-text">{chapter.title}</div>
                <div className="mt-2 text-xs text-text-2">{chapter.summary || 'No summary yet.'}</div>
              </button>
            ))}
          </div>
        </aside>
        <section className="flex min-w-0 flex-1 flex-col bg-bg">
          {activeChapter ? (
            <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar px-8 py-12" data-testid="chapter-editor">
              <div className="mx-auto max-w-5xl rounded-[32px] border border-border/70 bg-card px-10 py-12 shadow-2">
                <div className="mb-8 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Chapter Detail</div>
                    <div className="text-sm font-black text-text">Manual chapter editing is fully enabled.</div>
                  </div>
                  <button type="button" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" onClick={persistChapter} data-testid="save-chapter-btn">
                    Save Chapter
                  </button>
                </div>
                <input value={localChapterTitle} onChange={(event) => setLocalChapterTitle(event.target.value)} className="mb-6 w-full bg-transparent text-5xl font-black tracking-tight outline-none" placeholder="Chapter title" data-testid="chapter-title-input" />
                <textarea value={localChapterSummary} onChange={(event) => setLocalChapterSummary(event.target.value)} className="mb-6 h-28 w-full rounded-3xl border border-border bg-bg p-5 text-sm leading-relaxed text-text-2 outline-none" placeholder="Chapter summary" data-testid="chapter-summary-input" />
                <div className="grid gap-6 lg:grid-cols-2">
                  <textarea value={localChapterGoal} onChange={(event) => setLocalChapterGoal(event.target.value)} className="h-36 w-full rounded-3xl border border-border bg-bg p-5 text-sm leading-relaxed text-text-2 outline-none" placeholder="Chapter goal" data-testid="chapter-goal-input" />
                  <textarea value={localChapterNotes} onChange={(event) => setLocalChapterNotes(event.target.value)} className="h-36 w-full rounded-3xl border border-border bg-bg p-5 text-sm leading-relaxed text-text-2 outline-none" placeholder="Chapter notes" data-testid="chapter-notes-input" />
                </div>
                <div className="mt-8 rounded-3xl border border-border bg-bg-elev-1 p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Scenes in Chapter</div>
                    <button
                      type="button"
                      className="rounded-xl border border-border px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-2 hover:border-brand"
                      onClick={() => {
                        const nextSceneId = `scene_${Date.now()}`;
                        const chapterSceneCount = scenes.filter((scene) => scene.chapterId === activeChapter.id).length;
                        addScene({
                          id: nextSceneId,
                          chapterId: activeChapter.id,
                          title: `Scene ${chapterSceneCount + 1}`,
                          summary: '',
                          content: '',
                          orderIndex: chapterSceneCount,
                          povCharacterId: null,
                          linkedCharacterIds: [],
                          linkedEventIds: [],
                          linkedWorldItemIds: [],
                          status: 'draft',
                        });
                        updateChapter({ ...activeChapter, sceneIds: [...activeChapter.sceneIds, nextSceneId] });
                        setSelectedEntity('scene', nextSceneId);
                      }}
                      data-testid="chapter-add-scene-btn"
                    >
                      <Plus size={12} className="mr-2 inline" />
                      Add Scene
                    </button>
                  </div>
                  <div className="space-y-3">
                    {scenes.filter((scene) => scene.chapterId === activeChapter.id).map((scene) => (
                      <button key={scene.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand" onClick={() => setSelectedEntity('scene', scene.id)}>
                        <div>
                          <div className="text-sm font-bold text-text">{scene.title}</div>
                          <div className="mt-1 text-xs text-text-3">{scene.summary || 'No summary yet.'}</div>
                        </div>
                        <ChevronRight size={14} className="text-text-3" />
                      </button>
                    ))}
                    {!scenes.some((scene) => scene.chapterId === activeChapter.id) && (
                      <div className="rounded-2xl border border-dashed border-border bg-bg px-4 py-5 text-sm text-text-3">No scenes in this chapter yet.</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center text-text-3">No chapters yet.</div>
          )}
        </section>
      </div>
    );
  }

  if (sidebarSection === 'scripts') {
    const filteredScripts = scripts.filter((script) => `${script.title} ${script.summary}`.toLowerCase().includes(scriptQuery.toLowerCase()));
    return (
      <div className="flex h-full overflow-hidden bg-bg">
        <aside style={{ width: writingOutlineWidth }} className="flex h-full flex-col border-r border-border bg-bg-elev-1 shadow-1" data-testid="writing-scripts-sidebar">
          <div className="border-b border-border bg-bg-elev-2 p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Script Registry</div>
            <div className="mt-2 rounded-2xl border border-border bg-bg px-3 py-2">
              <div className="flex items-center gap-2"><Search size={13} /><input value={scriptQuery} onChange={(event) => setScriptQuery(event.target.value)} className="w-full bg-transparent text-sm outline-none" placeholder="Search scripts..." /></div>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2">
            {filteredScripts.map((script) => (
              <button
                key={script.id}
                type="button"
                className={cn('w-full rounded-2xl border px-4 py-3 text-left', activeScript?.id === script.id ? 'border-brand bg-selected' : 'border-border bg-bg hover:border-brand')}
                onClick={() => setSelectedEntity('script', script.id)}
                data-testid={`script-item-${script.id}`}
              >
                <div className="text-sm font-black text-text">{script.title}</div>
                <div className="mt-2 text-xs text-text-2">{script.summary}</div>
              </button>
            ))}
          </div>
        </aside>
        <section className="flex min-w-0 flex-1 flex-col bg-bg">
          <div className="flex items-center justify-between border-b border-border bg-bg-elev-1 px-6 py-3">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Script Draft</div>
              <div className="text-sm font-black text-text">{activeScript?.title || 'No script selected'}</div>
            </div>
            <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-2">{activeScript?.reviewState || 'idle'}</div>
          </div>
          {activeScript ? (
            <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar px-8 py-12">
              <div className="mx-auto max-w-5xl rounded-[32px] border border-border/70 bg-card px-10 py-12 shadow-2" data-testid="script-manuscript-panel">
                <input
                  value={activeScript.title}
                  readOnly
                  className="mb-6 w-full bg-transparent text-4xl font-black tracking-tight outline-none"
                />
                <div className="mb-6 grid gap-4 rounded-3xl border border-border bg-bg-elev-1 p-5 lg:grid-cols-3">
                  <InfoRow label="Mode" value={activeScript.mode} icon={<Type size={14} />} />
                  <InfoRow label="Episodes" value={String(activeScript.episodes.length)} icon={<BookOpen size={14} />} />
                  <InfoRow label="Linked scenes" value={activeScript.sourceSceneIds.join(', ') || 'None'} icon={<Clock size={14} />} />
                </div>
                <div className="mb-6 rounded-3xl border border-border bg-bg-elev-1 p-5">
                  <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Review Boundary</div>
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      review: {activeScript.reviewState}
                    </span>
                    <span className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      version: {activeScript.version}
                    </span>
                    <span className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      draft: {activeScript.draftPath || 'in-memory'}
                    </span>
                  </div>
                  <div className="mt-4 text-sm leading-relaxed text-text-2">
                    This script remains canonical project content, but any AI-generated rewrite must still route through proposals and Workbench review before replacing reviewed text.
                  </div>
                </div>
                <textarea
                  data-testid="script-editor"
                  className="min-h-[640px] w-full resize-none bg-transparent font-mono text-base leading-8 text-text-2 outline-none"
                  value={localScriptContent}
                  onChange={(event) => {
                    const value = event.target.value;
                    setLocalScriptContent(value);
                    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
                    saveTimeoutRef.current = setTimeout(() => {
                      if (!activeScript) return;
                      updateScript({ ...activeScript, content: value, updatedAt: new Date().toISOString() });
                      setLastActionStatus('Saved');
                    }, 1000);
                  }}
                />
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center text-text-3">No scripts yet.</div>
          )}
        </section>
      </div>
    );
  }

  if (sidebarSection === 'storyboards') {
    return (
      <div className="flex h-full overflow-hidden bg-bg">
        <aside style={{ width: writingOutlineWidth }} className="flex h-full flex-col border-r border-border bg-bg-elev-1 shadow-1 p-3 gap-2" data-testid="writing-storyboards-sidebar">
          {storyboards.map((storyboard) => (
            <button
              key={storyboard.id}
              type="button"
              className={cn('w-full rounded-2xl border px-4 py-3 text-left', activeStoryboard?.id === storyboard.id ? 'border-brand bg-selected' : 'border-border bg-bg hover:border-brand')}
              onClick={() => setSelectedEntity('storyboard', storyboard.id)}
              data-testid={`storyboard-item-${storyboard.id}`}
            >
              <div className="text-sm font-black text-text">{storyboard.title}</div>
              <div className="mt-2 text-xs text-text-2">{storyboard.visualStyleNotes}</div>
            </button>
          ))}
        </aside>
        <section className="flex min-w-0 flex-1 flex-col bg-bg">
          <div className="flex items-center justify-between border-b border-border bg-bg-elev-1 px-6 py-3">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Storyboard Preview</div>
              <div className="text-sm font-black text-text">{activeStoryboard?.title || 'No storyboard selected'}</div>
            </div>
            <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-2">{activeStoryboard?.status || 'idle'}</div>
          </div>
          {activeStoryboard ? (
            <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar px-8 py-10" data-testid="storyboard-panel">
            <div className="grid gap-4">
              {activeStoryboard.shots.map((shot) => (
                <div key={shot.id} className="rounded-2xl border border-border bg-card p-5 shadow-1">
                  <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{shot.id}</div>
                  <h3 className="mt-2 text-lg font-black text-text">{shot.title}</h3>
                  <p className="mt-2 text-sm text-text-2">{shot.summary}</p>
                  <div className="mt-4 rounded-xl border border-border bg-bg-elev-1 p-4 text-sm text-text-2">{shot.visualPrompt}</div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <span className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      characters: {shot.linkedCharacterIds.join(', ') || 'none'}
                    </span>
                    <span className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      world: {shot.linkedWorldItemIds.join(', ') || 'none'}
                    </span>
                    <span className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      duration: {shot.durationSeconds || 0}s
                    </span>
                  </div>
                </div>
              ))}
              <div className="rounded-2xl border border-border bg-card p-5 shadow-1">
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Prompt package</div>
                <div className="mt-3 text-sm text-text-2">{activeStoryboard.promptPackagePath || 'Pending package generation'}</div>
                <div className="mt-3 text-sm leading-relaxed text-text-2">
                  Storyboard output is reviewable structured input for downstream video orchestration. Provider execution remains adapter-driven and does not rewrite storyboard canon directly.
                </div>
              </div>
            </div>
          </div>
          ) : (
            <div className="flex flex-1 items-center justify-center text-text-3">No storyboards yet.</div>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      {!isWritingOutlineCollapsed && (
        <>
          <aside style={{ width: writingOutlineWidth }} className="flex h-full flex-col border-r border-border bg-bg-elev-1 shadow-1" data-testid="writing-sidebar">
            <div className="border-b border-border bg-bg-elev-2 p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.manuscript')}</div>
                  <div className="text-sm font-black text-text">Outline / Selection</div>
                </div>
                <button
                  type="button"
                  className="rounded-xl border border-border p-2 text-brand hover:border-brand"
                  onClick={() => {
                    const chapterId = activeChapter?.id || chapters[0]?.id;
                    if (!chapterId) return;
                    const nextSceneId = `scene_${Date.now()}`;
                    const chapterSceneCount = scenes.filter((scene) => scene.chapterId === chapterId).length;
                    addScene({
                      id: nextSceneId,
                      chapterId,
                      title: `Scene ${chapterSceneCount + 1}`,
                      summary: '',
                      content: '',
                      orderIndex: chapterSceneCount,
                      povCharacterId: null,
                      linkedCharacterIds: [],
                      linkedEventIds: [],
                      linkedWorldItemIds: [],
                      status: 'draft',
                    });
                    const chapter = chapters.find((entry) => entry.id === chapterId);
                    if (chapter) updateChapter({ ...chapter, sceneIds: [...chapter.sceneIds, nextSceneId] });
                    setSelectedEntity('scene', nextSceneId);
                  }}
                  data-testid="add-scene-btn"
                >
                  <Plus size={15} />
                </button>
                <button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" onClick={() => toggleWritingPane('outline', false)} data-testid="writing-outline-toggle">
                  <PanelLeft size={15} />
                </button>
              </div>
              <div className="rounded-2xl border border-border bg-bg px-3 py-2">
                <div className="flex items-center gap-2"><Search size={13} /><input value={sceneQuery} onChange={(event) => setSceneQuery(event.target.value)} className="w-full bg-transparent text-sm outline-none" placeholder="Search scenes..." /></div>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              <div className="border-b border-divider p-4">
                <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Recent</div>
                <div className="space-y-2">
                  {recentScenes.map((scene) => (
                    <button key={scene.id} type="button" className="w-full rounded-2xl border border-border bg-bg px-3 py-2 text-left text-sm text-text-2 hover:border-brand" onClick={() => setSelectedEntity('scene', scene.id)}>
                      {scene.title}
                    </button>
                  ))}
                </div>
              </div>
              {filteredChapters.map((chapter) => (
                <div key={chapter.id} className="border-b border-divider">
                  <div className="flex items-center gap-3 px-4 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-text-3">
                    <BookOpen size={13} className="text-brand-2" />
                    <span>{chapter.title}</span>
                  </div>
                  <div className="space-y-1 pb-3">
                    {chapter.visibleScenes.map((scene) => (
                      <button
                        type="button"
                        key={scene.id}
                        data-testid={`scene-item-${scene.id}`}
                        className={cn('group flex w-full items-center justify-between px-6 py-3 text-left transition-colors', activeScene?.id === scene.id ? 'bg-active text-text' : 'text-text-2 hover:bg-hover')}
                        onClick={() => setSelectedEntity('scene', scene.id)}
                        onContextMenu={(event) => {
                          event.preventDefault();
                          openContextMenu({
                            x: event.clientX,
                            y: event.clientY,
                            items: [
                              { id: 'scene-open', label: 'Open Scene', action: () => setSelectedEntity('scene', scene.id) },
                              { id: 'scene-context', label: 'Focus Narrative Context', action: () => toggleWritingPane('context', true) },
                            ],
                          });
                        }}
                      >
                        <span className="text-[11px] font-medium">{scene.title}</span>
                        <MoreVertical size={12} className="opacity-50" />
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </aside>
          <PaneResizeHandle panel="writingOutline" direction="right" testId="writing-outline-resizer" />
        </>
      )}

      <section className="flex min-w-0 flex-1 flex-col bg-bg">
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-1 px-6 py-3">
          <div className="flex items-center gap-3">
            <button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" onClick={() => toggleWritingPane('outline', isWritingOutlineCollapsed)} data-testid="writing-outline-reopen">
              {isWritingOutlineCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            </button>
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.draftMode')}</div>
              <div className="text-sm font-black text-text">{activeScene?.title || t('writing.idle')}</div>
            </div>
          </div>
          <button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" onClick={() => toggleWritingPane('context', isWritingContextCollapsed)} data-testid="writing-context-toggle">
            {isWritingContextCollapsed ? <PanelRight size={15} /> : <PanelLeft size={15} />}
          </button>
        </div>
        {activeScene ? (
          <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar px-8 py-12">
            <div className={cn('mx-auto rounded-[32px] border border-border/70 bg-card px-10 py-12 shadow-2', editorWidth === 'wide' ? 'max-w-[1200px]' : 'max-w-4xl')} data-testid="writing-manuscript-panel">
              <div className="mb-4 flex items-center gap-3 opacity-40"><Type size={12} className="text-brand" /><span className="text-[9px] font-black uppercase tracking-[0.4em]">{t('writing.draftMode')}</span></div>
              <input value={localTitle} onChange={(event) => {
                setLocalTitle(event.target.value);
                activeScene && updateScene({ ...activeScene, title: event.target.value });
              }} className="mb-10 w-full bg-transparent text-5xl font-black tracking-tight outline-none" placeholder={t('writing.sceneTitle')} />
              <div className="mb-8 grid gap-4 rounded-3xl border border-border bg-bg-elev-1 p-5 lg:grid-cols-3">
                <InfoRow label={t('writing.pov')} value={characters.find((character) => character.id === activeScene.povCharacterId)?.name || 'Unassigned'} icon={<Users size={14} />} />
                <InfoRow label={t('writing.events')} value={linkedEvents.map((event) => event.title).join(', ') || 'None'} icon={<Clock size={14} />} />
                <InfoRow label={t('writing.world')} value={linkedItems.map((item) => item.name).join(', ') || 'None'} icon={<Box size={14} />} />
              </div>
              <textarea
                data-testid="writing-editor"
                className="min-h-[640px] w-full resize-none bg-transparent font-serif text-xl leading-[2] text-text-2 outline-none"
                placeholder="The first sentence is always the hardest..."
                value={localContent}
                onChange={(event) => {
                  const value = event.target.value;
                  setLocalContent(value);
                  if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
                  saveTimeoutRef.current = setTimeout(() => activeScene && persistScene({ ...activeScene, content: value }), 1000);
                }}
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-text-3" data-testid="writing-idle"><Sparkles size={120} className="opacity-10" /></div>
        )}
      </section>

      {!isWritingContextCollapsed && (
        <>
          <PaneResizeHandle panel="writingContext" direction="left" testId="writing-context-resizer" />
          <aside style={{ width: writingContextWidth }} className="flex h-full flex-col border-l border-border bg-bg-elev-1 shadow-2" data-testid="context-panel">
            <div className="border-b border-border bg-bg-elev-2 p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.context')}</div>
                  <div className="text-sm font-black text-text">Narrative Context</div>
                </div>
                <button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" onClick={() => toggleWritingPane('context', false)} data-testid="writing-context-collapse">
                  <PanelRight size={15} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              <ContextSection title={t('writing.personas')} count={contextCharacters.length}>
                {contextCharacters.map((character) => (
                  <button key={character.id} type="button" data-testid="context-insert-character" className="flex w-full items-center justify-between rounded-2xl border border-transparent px-3 py-3 text-left text-sm text-text-2 hover:border-brand/30 hover:bg-selected" onClick={() => setSelectedEntity('character', character.id)}>
                    <span>{character.name}</span>
                    <Plus size={12} className="text-brand" />
                  </button>
                ))}
              </ContextSection>
              <ContextSection title={t('writing.chronology')} count={contextEvents.length}>
                {contextEvents.map((event) => (
                  <button key={event.id} type="button" data-testid="context-insert-event" className="w-full rounded-2xl border border-border bg-bg px-3 py-3 text-left hover:border-brand" onClick={() => setSelectedEntity('timeline_event', event.id)}>
                    <div className="text-sm font-bold text-text">{event.title}</div>
                    <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-text-3">{event.time || 'Timeline'}</div>
                  </button>
                ))}
              </ContextSection>
              <ContextSection title={t('writing.world')} count={contextWorldItems.length}>
                {contextWorldItems.map((item) => (
                  <button key={item.id} type="button" data-testid="context-insert-world-item" className="flex w-full items-center justify-between rounded-2xl border border-transparent px-3 py-3 text-left text-sm text-text-2 hover:border-brand/30 hover:bg-selected" onClick={() => setSelectedEntity('world_item', item.id)}>
                    <span>{item.name}</span>
                    <Plus size={12} className="text-brand" />
                  </button>
                ))}
              </ContextSection>
              <ContextSection title="Linked scenes" count={activeScene ? scenes.filter((scene) => scene.chapterId === activeScene.chapterId).length : 0}>
                {scenes.filter((scene) => scene.chapterId === activeScene?.chapterId).map((scene) => (
                  <button key={scene.id} type="button" className="w-full rounded-2xl border border-border bg-bg px-3 py-3 text-left hover:border-brand" onClick={() => setSelectedEntity('scene', scene.id)}>
                    <div className="text-sm font-bold text-text">{scene.title}</div>
                    <div className="mt-1 text-xs text-text-3">{scene.summary}</div>
                  </button>
                ))}
              </ContextSection>
            </div>
            <div className="border-t border-border bg-bg-elev-2 p-4">
              <div className="mb-3 text-[9px] font-black uppercase tracking-[0.3em] text-text-3">Neural Synthesis</div>
              <div className="grid grid-cols-2 gap-3">
                <button className="rounded-2xl border border-border bg-bg py-3 text-[9px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand" data-testid="editor-generate-scene-btn"><Zap size={14} className="mx-auto mb-2 text-brand" />{t('writing.generate')}</button>
                <button className="rounded-2xl border border-border bg-bg py-3 text-[9px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand" data-testid="editor-rewrite-btn"><Wand2 size={14} className="mx-auto mb-2 text-brand" />{t('writing.rewrite')}</button>
              </div>
            </div>
          </aside>
        </>
      )}
    </div>
  );
};

const ContextSection = ({ title, count, children }: { title: string; count: number; children: React.ReactNode }) => (
  <div className="border-b border-divider p-5">
    <div className="mb-4 flex items-center justify-between">
      <h4 className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{title}</h4>
      <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[9px] text-text-3">{count}</span>
    </div>
    <div className="space-y-2">{children}</div>
  </div>
);

const InfoRow = ({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) => (
  <div>
    <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{icon}<span>{label}</span></div>
    <div className="text-sm text-text-2">{value}</div>
  </div>
);

const mergeRecent = <T extends { id: string }>(primary: T[], secondary: T[], limit: number) => {
  const seen = new Set<string>();
  return [...primary, ...secondary].filter((entry) => {
    if (seen.has(entry.id)) return false;
    seen.add(entry.id);
    return true;
  }).slice(0, limit);
};
