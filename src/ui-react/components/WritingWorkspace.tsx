import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { BookOpen, ChevronLeft, ChevronRight, PanelLeft, PanelRight, Plus, Search, Sparkles } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { PaneResizeHandle } from './PaneResizeHandle';
import { cn } from '../utils';
import { useI18n } from '../i18n';

const now = () => new Date().toISOString();

export const WritingWorkspace = () => {
  const ui = useUIStore();
  const selectedEntity = useProjectStore((state) => state.selectedEntity);
  const setSelectedEntity = useProjectStore((state) => state.setSelectedEntity);
  const syncProjectUiState = useProjectStore((state) => state.syncProjectUiState);
  const location = useLocation();
  const [params] = useSearchParams();
  const [sceneQuery, setSceneQuery] = useState('');
  const [scriptQuery, setScriptQuery] = useState('');
  const routeSection = location.pathname.includes('/chapters')
    ? 'chapters'
    : location.pathname.includes('/scripts')
    ? 'scripts'
    : location.pathname.includes('/storyboards')
    ? 'storyboards'
    : 'scenes';

  useEffect(() => {
    const sceneId = params.get('scene');
    const chapterId = params.get('chapter');
    if (sceneId && selectedEntity.id !== sceneId) setSelectedEntity('scene', sceneId);
    else if (chapterId && selectedEntity.id !== chapterId) setSelectedEntity('chapter', chapterId);
  }, [params, selectedEntity.id, setSelectedEntity]);

  useEffect(() => {
    syncProjectUiState();
  }, [syncProjectUiState, ui.writingOutlineWidth, ui.writingContextWidth, ui.isWritingOutlineCollapsed, ui.isWritingContextCollapsed]);

  if (routeSection === 'chapters') return <ChapterEditor />;
  if (routeSection === 'scripts') return <ScriptEditor query={scriptQuery} setQuery={setScriptQuery} />;
  if (routeSection === 'storyboards') return <StoryboardEditor />;
  return <SceneEditor query={sceneQuery} setQuery={setSceneQuery} />;
};

const ChapterEditor = () => {
  const { t } = useI18n();
  const { chapters, scenes, selectedEntity, addChapter, updateChapter, addScene, setSelectedEntity } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const activeId = selectedEntity.type === 'chapter' ? selectedEntity.id : chapters[0]?.id || null;
  const chapter = chapters.find((entry) => entry.id === activeId) || chapters[0] || null;
  const [draft, setDraft] = useState(chapter);

  useEffect(() => setDraft(chapter), [chapter]);

  const groups = useMemo(() => {
    const buckets = [];
    for (let i = 0; i < chapters.length; i += 100) {
      buckets.push({ id: `bucket_${i}`, label: `Chapter ${i + 1}-${Math.min(i + 100, chapters.length)}`, items: chapters.slice(i, i + 100) });
    }
    return buckets;
  }, [chapters]);

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-80 border-r border-border bg-bg-elev-1" data-testid="writing-chapters-sidebar">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.chapters.title')}</div>
              <div className="text-sm font-black text-text">{t('writing.chapters.subtitle')}</div>
            </div>
            <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" data-testid="add-chapter-btn" onClick={() => {
              const id = `chap_${Date.now()}`;
              addChapter({ id, title: `Chapter ${chapters.length + 1}`, summary: '', goal: '', notes: '', sceneIds: [], orderIndex: chapters.length, status: 'draft' });
              setSelectedEntity('chapter', id);
              setLastActionStatus('Chapter created');
            }}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-3">
          {groups.map((group: any) => (
            <div key={group.id} className="mb-4 rounded-2xl border border-border bg-card">
              <div className="border-b border-divider px-4 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{group.label}</div>
              {group.items.map((item: any) => (
                <button key={item.id} type="button" data-testid={`chapter-item-${item.id}`} className={cn('block w-full border-b border-divider px-4 py-3 text-left last:border-b-0', item.id === chapter?.id ? 'bg-selected text-text' : 'text-text-2 hover:bg-hover')} onClick={() => setSelectedEntity('chapter', item.id)}>
                  <div className="text-sm font-black">{item.title}</div>
                  <div className="mt-1 line-clamp-1 text-xs text-text-3">{item.summary || t('writing.noSummary')}</div>
                </button>
              ))}
            </div>
          ))}
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto custom-scrollbar px-8 py-10">
        {draft ? (
          <div className="mx-auto max-w-5xl rounded-[32px] border border-border bg-card p-8 shadow-1" data-testid="chapter-editor">
            <div className="mb-8 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.chapter.detail.heading')}</div>
                <div className="text-sm font-black text-text">{t('writing.chapter.detail.subtitle')}</div>
              </div>
              <button type="button" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" data-testid="save-chapter-btn" onClick={() => { updateChapter(draft); setLastActionStatus('Chapter saved'); }}>{t('writing.chapter.saveBtn')}</button>
            </div>
            <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="mb-4 w-full bg-transparent text-5xl font-black tracking-tight outline-none" data-testid="chapter-title-input" />
            <textarea value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} className="mb-4 h-24 w-full rounded-3xl border border-border bg-bg p-5 text-sm text-text-2 outline-none" data-testid="chapter-summary-input" />
            <div className="grid gap-4 lg:grid-cols-2">
              <textarea value={draft.goal} onChange={(e) => setDraft({ ...draft, goal: e.target.value })} className="h-32 rounded-3xl border border-border bg-bg p-5 text-sm text-text-2 outline-none" data-testid="chapter-goal-input" />
              <textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} className="h-32 rounded-3xl border border-border bg-bg p-5 text-sm text-text-2 outline-none" data-testid="chapter-notes-input" />
            </div>
            <div className="mt-8 rounded-3xl border border-border bg-bg-elev-1 p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('writing.chapter.scenes.heading')}</div>
                <button type="button" className="rounded-xl border border-border px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-2 hover:border-brand" data-testid="chapter-add-scene-btn" onClick={() => {
                  const id = `scene_${Date.now()}`;
                  addScene({ id, chapterId: draft.id, title: `Scene ${draft.sceneIds.length + 1}`, summary: '', content: '', orderIndex: draft.sceneIds.length, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' });
                  const next = { ...draft, sceneIds: [...draft.sceneIds, id] };
                  updateChapter(next);
                  setDraft(next);
                  setSelectedEntity('scene', id);
                  setLastActionStatus('Scene created');
                }}>
                  <Plus size={12} className="mr-2 inline" />{t('writing.addScene')}
                </button>
              </div>
              <div className="space-y-3">
                {scenes.filter((entry) => entry.chapterId === draft.id).sort((a, b) => a.orderIndex - b.orderIndex).map((scene) => (
                  <button key={scene.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand" onClick={() => setSelectedEntity('scene', scene.id)}>
                    <div>
                      <div className="text-sm font-bold text-text">{scene.title}</div>
                      <div className="mt-1 text-xs text-text-3">{scene.summary || t('writing.noSummary')}</div>
                    </div>
                    <ChevronRight size={14} className="text-text-3" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : <Empty title={t('writing.empty.noChapters')} body={t('writing.empty.noChaptersBody')} />}
      </main>
    </div>
  );
};

const SceneEditor = ({ query, setQuery }: { query: string; setQuery: (value: string) => void }) => {
  const { t } = useI18n();
  const ui = useUIStore();
  const setLastActionStatus = useUIStore((state) => state.setLastActionStatus);
  const store = useProjectStore();
  const { chapters, scenes, characters, timelineEvents, worldItems, selectedEntity, setSelectedEntity, addChapter, addScene, updateScene, updateChapter } = store;
  const activeScene = scenes.find((entry) => entry.id === (selectedEntity.type === 'scene' ? selectedEntity.id : scenes[0]?.id)) || scenes[0] || null;
  const activeChapter = chapters.find((entry) => entry.id === activeScene?.chapterId) || chapters[0] || null;
  const [title, setTitle] = useState(activeScene?.title || '');
  const [content, setContent] = useState(activeScene?.content || '');
  const saveRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (activeScene) return;
    const chapterId = chapters[0]?.id || `chap_${Date.now()}`;
    if (!chapters.length) {
      addChapter({ id: chapterId, title: 'Chapter 1', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft' });
    }
    const sceneId = `scene_${Date.now()}`;
    addScene({ id: sceneId, chapterId, title: 'Scene 1', summary: '', content: '', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' });
    const bootstrapChapter = chapters.find((entry) => entry.id === chapterId);
    if (bootstrapChapter) {
      updateChapter({ ...bootstrapChapter, sceneIds: [...bootstrapChapter.sceneIds, sceneId] });
    }
    setSelectedEntity('scene', sceneId);
    setLastActionStatus('Scene created');
  }, [activeScene, addChapter, addScene, chapters, setLastActionStatus, setSelectedEntity, updateChapter]);

  useEffect(() => {
    setTitle(activeScene?.title || '');
    setContent(activeScene?.content || '');
  }, [activeScene?.id]);

  const groups = chapters.map((chapter) => ({
    chapter,
    scenes: scenes.filter((scene) => scene.chapterId === chapter.id && `${scene.title} ${scene.summary} ${scene.content}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => a.orderIndex - b.orderIndex),
  })).filter((group) => group.scenes.length);

  const linkedCharacters = characters.filter((entry) => activeScene?.linkedCharacterIds.includes(entry.id));
  const linkedEvents = timelineEvents.filter((entry) => activeScene?.linkedEventIds.includes(entry.id));
  const linkedItems = worldItems.filter((entry) => activeScene?.linkedWorldItemIds.includes(entry.id));

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      {!ui.isWritingOutlineCollapsed && <>
        <aside style={{ width: ui.writingOutlineWidth }} className="flex h-full flex-col border-r border-border bg-bg-elev-1" data-testid="writing-sidebar">
          <div className="border-b border-border bg-bg-elev-2 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div><div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.scenes.title')}</div><div className="text-sm font-black text-text">{t('writing.scenes.subtitle')}</div></div>
              <div className="flex items-center gap-2">
                <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" data-testid="add-scene-btn" onClick={() => {
                  const chapterId = activeChapter?.id || chapters[0]?.id;
                  if (!chapterId) return;
                  const id = `scene_${Date.now()}`;
                  const count = scenes.filter((scene) => scene.chapterId === chapterId).length;
                  addScene({ id, chapterId, title: `Scene ${count + 1}`, summary: '', content: '', orderIndex: count, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' });
                  const chapter = chapters.find((entry) => entry.id === chapterId);
                  if (chapter) updateChapter({ ...chapter, sceneIds: [...chapter.sceneIds, id] });
                  setSelectedEntity('scene', id);
                  setLastActionStatus('Scene created');
                }}><Plus size={15} /></button>
                <button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" data-testid="writing-outline-toggle" onClick={() => ui.toggleWritingPane('outline', false)}><PanelLeft size={15} /></button>
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-bg px-3 py-2"><div className="flex items-center gap-2"><Search size={13} /><input value={query} onChange={(e) => setQuery(e.target.value)} className="w-full bg-transparent text-sm outline-none" placeholder={t('writing.scenes.searchPlaceholder')} /></div></div>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            {groups.map((group) => (
              <div key={group.chapter.id} className="border-b border-divider">
                <div className="flex items-center gap-2 px-4 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3"><BookOpen size={12} className="text-brand-2" />{group.chapter.title}</div>
                {group.scenes.map((scene) => (
                  <button key={scene.id} type="button" data-testid={`scene-item-${scene.id}`} className={cn('flex w-full items-center justify-between px-6 py-3 text-left', scene.id === activeScene?.id ? 'bg-active text-text' : 'text-text-2 hover:bg-hover')} onClick={() => setSelectedEntity('scene', scene.id)}>
                    <span className="truncate text-[11px] font-medium">{scene.title}</span>
                    <ChevronRight size={12} className="opacity-50" />
                  </button>
                ))}
              </div>
            ))}
          </div>
        </aside>
        <PaneResizeHandle panel="writingOutline" direction="right" testId="writing-outline-resizer" />
      </>}

      <section className="flex min-w-0 flex-1 flex-col bg-bg">
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-1 px-6 py-3">
          <div className="flex items-center gap-3">
            <button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" data-testid="writing-outline-reopen" onClick={() => ui.toggleWritingPane('outline', ui.isWritingOutlineCollapsed)}>{ui.isWritingOutlineCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}</button>
            <div><div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.scene.draft')}</div><div className="text-sm font-black text-text">{activeScene?.title || t('writing.scene.noSelection')}</div></div>
          </div>
          <button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" data-testid="writing-context-toggle" onClick={() => ui.toggleWritingPane('context', ui.isWritingContextCollapsed)}>{ui.isWritingContextCollapsed ? <PanelRight size={15} /> : <PanelLeft size={15} />}</button>
        </div>
        {activeScene ? (
          <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar px-8 py-10">
            <div className={cn('mx-auto rounded-[32px] border border-border bg-card px-10 py-10 shadow-1', ui.editorWidth === 'wide' ? 'max-w-[1200px]' : 'max-w-4xl')} data-testid="writing-manuscript-panel">
              <input value={title} onChange={(e) => { setTitle(e.target.value); updateScene({ ...activeScene, title: e.target.value }); }} className="mb-8 w-full bg-transparent text-5xl font-black tracking-tight outline-none" placeholder="Scene title" />
              <div className="mb-6 grid gap-4 rounded-3xl border border-border bg-bg-elev-1 p-5 lg:grid-cols-3">
                <SmallInfo label={t('writing.scene.pov')} value={characters.find((entry) => entry.id === activeScene.povCharacterId)?.name || t('writing.scene.pov.unassigned')} />
                <SmallInfo label={t('writing.scene.events')} value={linkedEvents.map((entry) => entry.title).join(', ') || t('writing.none')} />
                <SmallInfo label={t('writing.scene.world')} value={linkedItems.map((entry) => entry.name).join(', ') || t('writing.none')} />
              </div>
              <textarea data-testid="writing-editor" className="min-h-[640px] w-full resize-none bg-transparent font-serif text-xl leading-[1.95] text-text-2 outline-none" value={content} onChange={(e) => { const value = e.target.value; setContent(value); if (saveRef.current) clearTimeout(saveRef.current); saveRef.current = setTimeout(() => { updateScene({ ...activeScene, content: value }); setLastActionStatus('Saved'); }, 700); }} placeholder={t('writing.scene.placeholder')} />
            </div>
          </div>
        ) : <Empty title={t('writing.empty.idle')} body={t('writing.empty.idleBody')} />}
      </section>

      {!ui.isWritingContextCollapsed && <>
        <PaneResizeHandle panel="writingContext" direction="left" testId="writing-context-resizer" />
        <aside style={{ width: ui.writingContextWidth }} className="flex h-full flex-col border-l border-border bg-bg-elev-1" data-testid="context-panel">
          <div className="border-b border-border bg-bg-elev-2 p-4"><div className="mb-3 flex items-center justify-between"><div><div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.context.title')}</div><div className="text-sm font-black text-text">{t('writing.context.subtitle')}</div></div><button type="button" className="rounded-xl border border-border p-2 text-text-2 hover:border-brand" data-testid="writing-context-collapse" onClick={() => ui.toggleWritingPane('context', false)}><PanelRight size={15} /></button></div></div>
          <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-4">
            <SideBlock title={t('writing.context.characters')} items={linkedCharacters.map((entry) => entry.name)} />
            <SideBlock title={t('writing.context.timeline')} items={linkedEvents.map((entry) => entry.title)} />
            <SideBlock title={t('writing.scene.world')} items={linkedItems.map((entry) => entry.name)} />
          </div>
        </aside>
      </>}
    </div>
  );
};

const ScriptEditor = ({ query, setQuery }: { query: string; setQuery: (value: string) => void }) => {
  const { t } = useI18n();
  const { scripts, scenes, storyboards, characters, selectedEntity, setSelectedEntity, addScript, updateScript } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const filtered = scripts.filter((script) => `${script.title} ${script.summary}`.toLowerCase().includes(query.toLowerCase()));
  const active = scripts.find((entry) => entry.id === (selectedEntity.type === 'script' ? selectedEntity.id : filtered[0]?.id || scripts[0]?.id)) || null;
  const [draft, setDraft] = useState(active);
  useEffect(() => setDraft(active), [active]);

  return <div className="flex h-full overflow-hidden bg-bg">
    <aside className="w-80 border-r border-border bg-bg-elev-1" data-testid="writing-scripts-sidebar">
      <div className="border-b border-border bg-bg-elev-2 p-4">
        <div className="mb-3 flex items-center justify-between"><div><div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.scripts.title')}</div><div className="text-sm font-black text-text">{t('writing.scripts.subtitle')}</div></div><button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" data-testid="add-script-btn" onClick={() => { const id = `script_${Date.now()}`; addScript({ id, title: `Script ${scripts.length + 1}`, mode: 'adaptation', summary: '', sourceSceneIds: [], sourceChapterIds: [], linkedCharacterIds: [], linkedWorldItemIds: [], status: 'draft', reviewState: 'pending', version: 1, draftPath: null, content: '', episodes: [], createdAt: now(), updatedAt: now() }); setSelectedEntity('script', id); setLastActionStatus('Script created'); }}><Plus size={16} /></button></div>
        <div className="rounded-2xl border border-border bg-bg px-3 py-2"><div className="flex items-center gap-2"><Search size={13} /><input value={query} onChange={(e) => setQuery(e.target.value)} className="w-full bg-transparent text-sm outline-none" placeholder={t('writing.scripts.searchPlaceholder')} /></div></div>
      </div>
      <div className="h-full overflow-y-auto custom-scrollbar p-3">{filtered.map((script) => <button key={script.id} type="button" data-testid={`script-item-${script.id}`} className={cn('mb-2 w-full rounded-2xl border px-4 py-3 text-left', active?.id === script.id ? 'border-brand bg-selected' : 'border-border bg-card hover:border-brand')} onClick={() => setSelectedEntity('script', script.id)}><div className="text-sm font-black text-text">{script.title}</div><div className="mt-1 line-clamp-2 text-xs text-text-3">{script.summary || t('writing.noSummary')}</div></button>)}</div>
    </aside>
    <main className="flex-1 overflow-y-auto custom-scrollbar px-8 py-10">{draft ? <div className="mx-auto max-w-5xl rounded-[32px] border border-border bg-card p-8 shadow-1"><div className="mb-8 flex items-center justify-between"><div><div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.script.draft')}</div><div className="text-sm font-black text-text">{t('writing.script.subtitle')}</div></div><button type="button" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" onClick={() => { updateScript({ ...draft, updatedAt: now() }); setLastActionStatus('Script saved'); }}>{t('writing.script.saveBtn')}</button></div><input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="mb-4 w-full bg-transparent text-5xl font-black tracking-tight outline-none" /><textarea value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} className="mb-4 h-24 w-full rounded-3xl border border-border bg-bg p-5 text-sm text-text-2 outline-none" placeholder={t('writing.script.summaryPlaceholder')} /><div className="mb-6 grid gap-4 rounded-3xl border border-border bg-bg-elev-1 p-5 lg:grid-cols-4"><SmallInfo label={t('writing.script.mode')} value={draft.mode} /><SmallInfo label={t('writing.script.episodes')} value={String(draft.episodes.length)} /><SmallInfo label={t('writing.script.sourceScenes')} value={draft.sourceSceneIds.length ? draft.sourceSceneIds.map((id) => scenes.find((scene) => scene.id === id)?.title || id).join(', ') : t('writing.none')} /><SmallInfo label={t('writing.script.storyboards')} value={String(storyboards.filter((entry) => entry.scriptId === draft.id).length)} /></div><div className="mb-4 flex flex-wrap gap-2">{(draft.linkedCharacterIds.length ? draft.linkedCharacterIds : characters.slice(0, 3).map((entry) => entry.id)).map((id) => <span key={id} className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{characters.find((entry) => entry.id === id)?.name || id}</span>)}</div><textarea data-testid="script-editor" className="min-h-[640px] w-full resize-none rounded-3xl border border-border bg-bg p-6 font-mono text-sm leading-7 text-text-2 outline-none" value={draft.content} onChange={(e) => setDraft({ ...draft, content: e.target.value })} placeholder={t('writing.script.placeholder')} /></div> : <Empty title={t('writing.empty.noScripts')} body={t('writing.empty.noScriptsBody')} />}</main>
  </div>;
};

const StoryboardEditor = () => {
  const { t } = useI18n();
  const { storyboards, scripts, characters, worldItems, selectedEntity, setSelectedEntity, addStoryboard, updateStoryboard } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const active = storyboards.find((entry) => entry.id === (selectedEntity.type === 'storyboard' ? selectedEntity.id : storyboards[0]?.id)) || null;
  const [draft, setDraft] = useState(active);
  useEffect(() => setDraft(active), [active]);

  return <div className="flex h-full overflow-hidden bg-bg">
    <aside className="w-80 border-r border-border bg-bg-elev-1" data-testid="writing-storyboards-sidebar">
      <div className="border-b border-border bg-bg-elev-2 p-4"><div className="mb-3 flex items-center justify-between"><div><div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.storyboards.title')}</div><div className="text-sm font-black text-text">{t('writing.storyboards.subtitle')}</div></div><button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => { const id = `storyboard_${Date.now()}`; const linked = scripts[0]; addStoryboard({ id, scriptId: linked?.id || '', episodeId: linked?.episodes[0]?.id || `episode_${Date.now()}`, title: `Storyboard ${storyboards.length + 1}`, shots: [{ id: `shot_${Date.now()}`, title: 'Opening shot', summary: '', visualPrompt: '', linkedCharacterIds: [], linkedWorldItemIds: [], durationSeconds: 5 }], visualStyleNotes: '', assetRefs: [], promptPackagePath: null, status: 'draft', createdAt: now(), updatedAt: now() }); setSelectedEntity('storyboard', id); setLastActionStatus('Storyboard created'); }}><Plus size={16} /></button></div></div>
      <div className="h-full overflow-y-auto custom-scrollbar p-3">{storyboards.map((storyboard) => <button key={storyboard.id} type="button" data-testid={`storyboard-item-${storyboard.id}`} className={cn('mb-2 w-full rounded-2xl border px-4 py-3 text-left', draft?.id === storyboard.id ? 'border-brand bg-selected' : 'border-border bg-card hover:border-brand')} onClick={() => setSelectedEntity('storyboard', storyboard.id)}><div className="text-sm font-black text-text">{storyboard.title}</div><div className="mt-1 line-clamp-2 text-xs text-text-3">{storyboard.visualStyleNotes || t('writing.storyboard.styleNotesPlaceholder')}</div></button>)}</div>
    </aside>
    <main className="flex-1 overflow-y-auto custom-scrollbar px-8 py-10">{draft ? <div className="mx-auto max-w-6xl rounded-[32px] border border-border bg-card p-8 shadow-1" data-testid="storyboard-panel"><div className="mb-8 flex items-center justify-between"><div><div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('writing.storyboard.heading')}</div><div className="text-sm font-black text-text">{t('writing.storyboard.subtitle')}</div></div><button type="button" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" onClick={() => { updateStoryboard({ ...draft, updatedAt: now() }); setLastActionStatus('Storyboard saved'); }}>{t('writing.storyboard.saveBtn')}</button></div><input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="mb-4 w-full bg-transparent text-5xl font-black tracking-tight outline-none" /><textarea value={draft.visualStyleNotes} onChange={(e) => setDraft({ ...draft, visualStyleNotes: e.target.value })} className="mb-4 h-24 w-full rounded-3xl border border-border bg-bg p-5 text-sm text-text-2 outline-none" placeholder={t('writing.storyboard.styleNotesPlaceholder')} /><select value={draft.scriptId} onChange={(e) => setDraft({ ...draft, scriptId: e.target.value })} className="mb-6 w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">{scripts.map((script) => <option key={script.id} value={script.id}>{script.title}</option>)}</select><div className="space-y-4">{draft.shots.map((shot, index) => <div key={shot.id} className="rounded-3xl border border-border bg-bg-elev-1 p-5"><div className="mb-4 flex items-center justify-between"><div className="text-[10px] font-black uppercase tracking-[0.18em] text-brand-2">{t('writing.storyboard.shot')} {index + 1}</div><button type="button" className="rounded-xl border border-border px-3 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-2 hover:border-brand" onClick={() => setDraft({ ...draft, shots: draft.shots.filter((entry) => entry.id !== shot.id) })}>{t('writing.storyboard.removeShot')}</button></div><input value={shot.title} onChange={(e) => setDraft(updateShot(draft, shot.id, { title: e.target.value }))} className="mb-3 w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('writing.storyboard.shotTitle')} /><textarea value={shot.summary} onChange={(e) => setDraft(updateShot(draft, shot.id, { summary: e.target.value }))} className="mb-3 h-24 w-full rounded-3xl border border-border bg-bg p-4 text-sm text-text-2 outline-none" placeholder={t('writing.storyboard.shotSummary')} /><textarea value={shot.visualPrompt} onChange={(e) => setDraft(updateShot(draft, shot.id, { visualPrompt: e.target.value }))} className="h-24 w-full rounded-3xl border border-border bg-bg p-4 text-sm text-text-2 outline-none" placeholder={t('writing.storyboard.visualPrompt')} /><div className="mt-3 flex flex-wrap gap-2">{shot.linkedCharacterIds.map((id) => <span key={id} className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{characters.find((entry) => entry.id === id)?.name || id}</span>)}{shot.linkedWorldItemIds.map((id) => <span key={id} className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{worldItems.find((entry) => entry.id === id)?.name || id}</span>)}</div></div>)}</div><button type="button" className="mt-5 rounded-xl border border-border px-4 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-text-2 hover:border-brand" onClick={() => setDraft({ ...draft, shots: [...draft.shots, { id: `shot_${Date.now()}`, title: `Shot ${draft.shots.length + 1}`, summary: '', visualPrompt: '', linkedCharacterIds: [], linkedWorldItemIds: [], durationSeconds: 5 }] })}><Plus size={12} className="mr-2 inline" />{t('writing.storyboard.addShot')}</button></div> : <Empty title={t('writing.empty.noStoryboards')} body={t('writing.empty.noStoryboardsBody')} />}</main>
  </div>;
};

const SmallInfo = ({ label, value }: { label: string; value: string }) => <div><div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{label}</div><div className="text-sm text-text-2">{value}</div></div>;
const SideBlock = ({ title, items }: { title: string; items: string[] }) => {
  const { t } = useI18n();
  return <div className="rounded-2xl border border-border bg-bg p-4"><div className="mb-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{title}</div><div className="space-y-2">{items.length ? items.map((item) => <div key={item} className="rounded-xl border border-border bg-bg-elev-1 px-3 py-2 text-sm text-text-2">{item}</div>) : <div className="text-sm text-text-3">{t('writing.none')}</div>}</div></div>;
};
const Empty = ({ title, body }: { title: string; body: string }) => <div className="flex min-h-[460px] flex-col items-center justify-center text-center text-text-3"><Sparkles size={96} className="mb-6 opacity-10" /><div className="text-lg font-black text-text">{title}</div><div className="mt-3 max-w-lg text-sm leading-relaxed text-text-2">{body}</div></div>;
const updateShot = (storyboard: any, shotId: string, partial: Record<string, unknown>) => ({ ...storyboard, shots: storyboard.shots.map((shot: any) => shot.id === shotId ? { ...shot, ...partial } : shot) });
