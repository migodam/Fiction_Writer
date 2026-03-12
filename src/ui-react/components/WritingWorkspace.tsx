import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProjectStore, useUIStore } from '../store';
import { Plus, MoreVertical, Search, Zap, BookOpen, Type, Sparkles, Wand2, Clock, Users, Box } from 'lucide-react';
import { useI18n } from '../i18n';

export const WritingWorkspace = () => {
  const { chapters, scenes, characters, timelineEvents, worldItems, selectedEntity, setSelectedEntity, updateScene } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const [searchParams] = useSearchParams();

  const requestedScene = searchParams.get('scene');
  const activeSceneId = selectedEntity.type === 'scene' ? selectedEntity.id : requestedScene || scenes[0]?.id;
  const activeScene = scenes.find((scene) => scene.id === activeSceneId);
  const linkedItems = worldItems.filter((item) => activeScene?.linkedWorldItemIds.includes(item.id));
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const [localContent, setLocalContent] = useState(activeScene?.content || '');
  const [localTitle, setLocalTitle] = useState(activeScene?.title || '');

  useEffect(() => {
    if (requestedScene) {
      setSelectedEntity('scene', requestedScene);
    }
  }, [requestedScene, setSelectedEntity]);

  useEffect(() => {
    if (activeScene) {
      setLocalContent(activeScene.content);
      setLocalTitle(activeScene.title);
    }
  }, [activeScene?.id]);

  const persistScene = (nextScene: typeof activeScene) => {
    if (nextScene) {
      updateScene(nextScene);
      setLastActionStatus('Saved');
    }
  };

  const handleContentChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value;
    setLocalContent(value);
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      if (activeScene) {
        persistScene({ ...activeScene, content: value });
      }
    }, 1200);
  };

  const handleTitleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setLocalTitle(value);
    if (activeScene) {
      updateScene({ ...activeScene, title: value });
    }
  };

  return (
    <div className="flex h-full bg-bg">
      <div className="w-72 border-r border-border flex flex-col bg-bg-elev-1 shadow-1" data-testid="writing-sidebar">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
          <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('writing.manuscript')}</h3>
          <button className="p-1 hover:bg-hover rounded-lg text-brand transition-colors" title="New Chapter"><Plus size={16} /></button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {chapters.map((chapter) => (
            <div key={chapter.id} className="mb-1">
              <div className="px-4 py-2.5 flex items-center gap-3 hover:bg-hover cursor-pointer group transition-all">
                <BookOpen size={14} className="text-brand-2" />
                <span className="text-[11px] font-black text-text-2 uppercase tracking-widest">{chapter.title}</span>
              </div>
              <div className="ml-5 border-l border-divider space-y-0.5 mb-2">
                {scenes.filter((scene) => scene.chapterId === chapter.id).map((scene) => (
                  <div key={scene.id} data-testid={`scene-item-${scene.id}`} className={`px-6 py-2.5 flex items-center justify-between hover:bg-selected cursor-pointer group transition-all relative ${activeSceneId === scene.id ? 'bg-active border-r-2 border-brand text-text' : 'text-text-3'}`} onClick={() => setSelectedEntity('scene', scene.id)}>
                    <span className={`text-[11px] font-medium transition-colors ${activeSceneId === scene.id ? 'text-text' : 'group-hover:text-text-2'}`}>{scene.title}</span>
                    <MoreVertical size={12} className="opacity-0 group-hover:opacity-100 text-text-3" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col items-center bg-bg relative">
        {activeScene ? (
          <div className="w-full max-w-4xl px-12 py-20 bg-card shadow-2 border-x border-border/50">
            <div className="flex items-center gap-3 mb-4 opacity-30"><Type size={12} className="text-brand" /><span className="text-[9px] font-black uppercase tracking-[0.4em]">{t('writing.draftMode')}</span></div>
            <input className="w-full bg-transparent text-5xl font-serif font-black text-text mb-10 outline-none tracking-tight focus:text-brand transition-colors" placeholder={t('writing.sceneTitle')} value={localTitle} onChange={handleTitleChange} />
            <div className="mb-8 grid gap-4 rounded-2xl border border-border bg-bg-elev-1 p-5 shadow-inner lg:grid-cols-3">
              <InfoRow label={t('writing.pov')} value={characters.find((character) => character.id === activeScene.povCharacterId)?.name || 'Unassigned'} icon={<Users size={14} />} />
              <InfoRow label={t('writing.events')} value={activeScene.linkedEventIds.map((id) => timelineEvents.find((event) => event.id === id)?.title || id).join(', ') || 'None'} icon={<Clock size={14} />} />
              <InfoRow label={t('writing.world')} value={linkedItems.map((item) => item.name).join(', ') || 'None'} icon={<Box size={14} />} />
            </div>
            <textarea data-testid="writing-editor" className="w-full min-h-[500px] bg-transparent text-xl leading-[2] text-text-2 outline-none resize-none font-serif placeholder:text-text-3/5 selection:bg-brand/30 selection:text-white" placeholder="The first sentence is always the hardest..." value={localContent} onChange={handleContentChange} />
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-text-3 select-none" data-testid="writing-idle"><Sparkles size={120} className="opacity-5 mb-8 animate-pulse" /><p className="text-[11px] font-black uppercase tracking-[0.5em] opacity-40">{t('writing.idle')}</p><p className="text-[9px] mt-4 opacity-20 uppercase tracking-widest font-medium">{t('writing.idleBody')}</p></div>
        )}
      </div>

      <aside className="w-80 border-l border-border bg-bg-elev-1 flex flex-col shadow-2 z-10" data-testid="context-panel">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
          <div className="flex items-center gap-3"><Sparkles size={16} className="text-brand" /><span className="text-[10px] font-black uppercase tracking-[0.25em] text-text-2">{t('writing.context')}</span></div>
          <button className="p-1.5 hover:bg-hover rounded-lg text-text-3 hover:text-text transition-colors"><Search size={14} /></button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <ContextSection title={t('writing.personas')} count={characters.length}>
            {characters.map((character) => (
              <button key={character.id} className="group flex items-center justify-between text-[11px] p-2.5 hover:bg-selected rounded-xl cursor-pointer text-text-2 hover:text-text transition-all border border-transparent hover:border-brand/20 w-full text-left" data-testid="context-insert-character" onClick={() => setSelectedEntity('character', character.id)}>
                <span className="truncate font-medium">{character.name}</span>
                <Plus size={12} className="text-brand opacity-0 group-hover:opacity-100 transition-all" />
              </button>
            ))}
          </ContextSection>
          <ContextSection title={t('writing.chronology')} count={timelineEvents.length}>
            {timelineEvents.map((event) => (
              <button key={event.id} className="group flex flex-col gap-1 p-3 hover:bg-selected rounded-xl cursor-pointer transition-all border border-border hover:border-brand/30 shadow-sm w-full text-left" data-testid="context-insert-event" onClick={() => setSelectedEntity('timeline_event', event.id)}>
                <div className="flex items-center justify-between"><span className="text-[11px] text-text-2 font-bold truncate leading-tight">{event.title}</span><Plus size={12} className="text-brand opacity-0 group-hover:opacity-100 transition-all" /></div>
                <div className="flex items-center gap-1.5 text-[9px] text-text-3 font-bold uppercase tracking-widest opacity-60"><Clock size={8} /> {event.time || 'Point in time'}</div>
              </button>
            ))}
          </ContextSection>
          <ContextSection title={t('writing.world')} count={linkedItems.length}>
            {linkedItems.map((item) => (
              <button key={item.id} className="group flex items-center justify-between text-[11px] p-2.5 hover:bg-selected rounded-xl cursor-pointer text-text-2 hover:text-text transition-all border border-transparent hover:border-brand/20 w-full text-left" onClick={() => setSelectedEntity('world_item', item.id)} data-testid="context-insert-world-item">
                <span className="truncate font-medium">{item.name}</span>
                <Plus size={12} className="text-brand opacity-0 group-hover:opacity-100 transition-all" />
              </button>
            ))}
          </ContextSection>
        </div>
        <div className="p-4 bg-bg-elev-2 border-t border-border flex flex-col gap-3 shadow-2">
          <div className="flex items-center gap-2 mb-1 ml-1"><Wand2 size={12} className="text-brand" /><div className="text-[9px] font-black text-text-3 uppercase tracking-[0.3em]">Neural Synthesis</div></div>
          <div className="grid grid-cols-2 gap-3">
            <button className="flex flex-col items-center justify-center gap-1.5 py-3 bg-bg border border-border hover:border-brand/40 hover:bg-hover rounded-xl text-[9px] font-black uppercase tracking-widest text-text-3 hover:text-text transition-all group" data-testid="editor-generate-scene-btn"><Zap size={14} className="group-hover:text-brand transition-colors" />{t('writing.generate')}</button>
            <button className="flex flex-col items-center justify-center gap-1.5 py-3 bg-bg border border-border hover:border-brand/40 hover:bg-hover rounded-xl text-[9px] font-black uppercase tracking-widest text-text-3 hover:text-text transition-all group" data-testid="editor-rewrite-btn"><Sparkles size={14} className="group-hover:text-brand transition-colors" />{t('writing.rewrite')}</button>
          </div>
        </div>
      </aside>
    </div>
  );
};

const ContextSection = ({ title, count, children }: { title: string; count: number; children: React.ReactNode }) => (
  <div className="p-5 border-b border-divider hover:bg-bg-elev-2/30 transition-colors">
    <div className="flex items-center justify-between mb-5">
      <h4 className="text-[10px] font-black text-text-3 uppercase tracking-[0.25em]">{title}</h4>
      <span className="text-[9px] px-2 py-0.5 bg-bg-elev-2 border border-border rounded-full text-text-3 font-bold">{count}</span>
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
