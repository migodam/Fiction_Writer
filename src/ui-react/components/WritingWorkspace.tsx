import React, { useEffect, useState, useRef } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { 
    FileText, Users, Clock, Info, Plus, ChevronDown, 
    ChevronRight, Book, MoreVertical, Search, Zap,
    BookOpen, Layers, Type, Sparkles, Wand2
} from 'lucide-react';

export const WritingWorkspace = () => {
  const { 
      chapters, scenes, characters, timelineEvents, 
      selectedEntity, setSelectedEntity,
      addScene, updateScene
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  
  const activeSceneId = selectedEntity.type === 'scene' ? selectedEntity.id : scenes[0]?.id;
  const activeScene = scenes.find(s => s.id === activeSceneId);

  const [localContent, setLocalContent] = useState(activeScene?.content || '');
  const [localTitle, setLocalTitle] = useState(activeScene?.title || '');
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
      if (activeScene) {
          setLocalContent(activeScene.content);
          setLocalTitle(activeScene.title);
      }
  }, [activeSceneId]);

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setLocalContent(val);
    
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    
    saveTimeoutRef.current = setTimeout(() => {
      if (activeScene) {
          updateScene({ ...activeScene, content: val });
          setLastActionStatus('Saved');
      }
    }, 1500);
  };

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value;
      setLocalTitle(val);
      if (activeScene) {
          updateScene({ ...activeScene, title: val });
      }
  };

  return (
    <div className="flex h-full bg-bg">
      {/* Writing Sidebar (Chapters & Scenes) - Workspace Left Panel */}
      <div className="w-72 border-r border-border flex flex-col bg-bg-elev-1 shadow-1" data-testid="writing-sidebar">
          <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
              <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Manuscript</h3>
              <button 
                className="p-1 hover:bg-hover rounded-lg text-brand transition-colors"
                title="New Chapter"
              >
                <Plus size={16} />
              </button>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar">
              {chapters.map(chap => (
                  <div key={chap.id} className="mb-1">
                      <div className="px-4 py-2.5 flex items-center gap-3 hover:bg-hover cursor-pointer group transition-all">
                          <ChevronDown size={14} className="text-text-3 group-hover:text-text-2 transition-colors" />
                          <BookOpen size={14} className="text-brand-2" />
                          <span className="text-[11px] font-black text-text-2 uppercase tracking-widest">{chap.title}</span>
                      </div>
                      <div className="ml-5 border-l border-divider space-y-0.5 mb-2">
                          {scenes.filter(s => s.chapterId === chap.id).map(scene => (
                              <div 
                                key={scene.id}
                                data-testid={`scene-item-${scene.id}`}
                                className={`px-6 py-2.5 flex items-center justify-between hover:bg-selected cursor-pointer group transition-all relative ${
                                    activeSceneId === scene.id ? 'bg-active border-r-2 border-brand text-text' : 'text-text-3'
                                }`}
                                onClick={() => setSelectedEntity('scene', scene.id)}
                              >
                                  <span className={`text-[11px] font-medium transition-colors ${activeSceneId === scene.id ? 'text-text' : 'group-hover:text-text-2'}`}>{scene.title}</span>
                                  <MoreVertical size={12} className="opacity-0 group-hover:opacity-100 text-text-3 hover:text-text transition-opacity" />
                                  {activeSceneId === scene.id && (
                                      <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-brand/30"></div>
                                  )}
                              </div>
                          ))}
                      </div>
                  </div>
              ))}
              {chapters.length === 0 && (
                  <div className="p-12 text-center opacity-20">
                      <BookOpen size={40} className="mx-auto mb-4" />
                      <p className="text-[10px] font-black uppercase tracking-widest">No Narrative Units</p>
                  </div>
              )}
          </div>
      </div>

      {/* Editor Main */}
      <div className="flex-1 flex flex-col items-center bg-bg relative">
        {activeScene ? (
            <div className="w-full max-w-4xl px-12 py-24 bg-card shadow-2 border-x border-border/50">
                <div className="flex items-center gap-3 mb-4 opacity-30">
                    <Type size={12} className="text-brand" />
                    <span className="text-[9px] font-black uppercase tracking-[0.4em]">Draft Mode</span>
                </div>
                <input 
                    className="w-full bg-transparent text-5xl font-serif font-black text-text mb-16 outline-none placeholder:text-text-3/10 tracking-tight focus:text-brand transition-colors"
                    placeholder="Scene Title"
                    value={localTitle}
                    onChange={handleTitleChange}
                />
                <div className="flex-1 w-full min-h-[500px] flex flex-col">
                    <textarea 
                        data-testid="writing-editor"
                        className="w-full flex-1 min-h-[500px] bg-transparent text-xl leading-[2] text-text-2 outline-none resize-none font-serif placeholder:text-text-3/5 selection:bg-brand/30 selection:text-white"
                        style={{ opacity: 1, visibility: 'visible', display: 'block' }}
                        placeholder="The first sentence is always the hardest..."
                        value={localContent}
                        onChange={handleContentChange}
                    />
                </div>
            </div>
        ) : (
            <div className="h-full flex flex-col items-center justify-center text-text-3 select-none" data-testid="writing-idle">
                <Sparkles size={120} className="opacity-5 mb-8 animate-pulse" />
                <p className="text-[11px] font-black uppercase tracking-[0.5em] opacity-40">Workspace Idle</p>
                <p className="text-[9px] mt-4 opacity-20 uppercase tracking-widest font-medium">Select a scene to begin weaving the narrative</p>
            </div>
        )}
      </div>

      {/* Context Panel (Right) */}
      <aside className="w-80 border-l border-border bg-bg-elev-1 flex flex-col shadow-2 z-10" data-testid="context-panel">
         <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
           <div className="flex items-center gap-3">
                <Sparkles size={16} className="text-brand" />
                <span className="text-[10px] font-black uppercase tracking-[0.25em] text-text-2">Narrative Context</span>
           </div>
           <button className="p-1.5 hover:bg-hover rounded-lg text-text-3 hover:text-text transition-colors">
               <Search size={14} />
           </button>
         </div>
         
         <div className="flex-1 overflow-y-auto custom-scrollbar">
            {/* Characters Section */}
            <div className="p-5 border-b border-divider hover:bg-bg-elev-2/30 transition-colors">
               <div className="flex items-center justify-between mb-5">
                    <h4 className="text-[10px] font-black text-text-3 uppercase tracking-[0.25em] flex items-center gap-2.5">
                        <Users size={14} className="text-blue" /> Personas
                    </h4>
                    <span className="text-[9px] px-2 py-0.5 bg-bg-elev-2 border border-border rounded-full text-text-3 font-bold">{characters.length}</span>
               </div>
               <div className="space-y-1.5">
                    {characters.map(c => (
                        <div 
                            key={c.id} 
                            className="group flex items-center justify-between text-[11px] p-2.5 hover:bg-selected rounded-xl cursor-pointer text-text-2 hover:text-text transition-all border border-transparent hover:border-brand/20" 
                            data-testid="context-insert-character"
                            onClick={() => setSelectedEntity('character', c.id)}
                        >
                            <span className="truncate font-medium">{c.name}</span>
                            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-all translate-x-2 group-hover:translate-x-0">
                                <Plus size={12} className="text-brand" />
                                <ChevronRight size={12} className="text-text-3" />
                            </div>
                        </div>
                    ))}
                    {characters.length === 0 && (
                        <div className="text-[10px] text-text-3 italic text-center py-6 border border-dashed border-divider rounded-xl opacity-50">
                            No entities detected
                        </div>
                    )}
               </div>
            </div>

            {/* Timeline Section */}
            <div className="p-5 border-b border-divider hover:bg-bg-elev-2/30 transition-colors">
               <div className="flex items-center justify-between mb-5">
                    <h4 className="text-[10px] font-black text-text-3 uppercase tracking-[0.25em] flex items-center gap-2.5">
                        <Clock size={14} className="text-amber" /> Chronology
                    </h4>
                    <span className="text-[9px] px-2 py-0.5 bg-bg-elev-2 border border-border rounded-full text-text-3 font-bold">{timelineEvents.length}</span>
               </div>
               <div className="space-y-2">
                    {timelineEvents.map(e => (
                        <div 
                            key={e.id} 
                            className="group flex flex-col gap-1 p-3 hover:bg-selected rounded-xl cursor-pointer transition-all border border-border hover:border-brand/30 shadow-sm" 
                            data-testid="context-insert-event"
                            onClick={() => setSelectedEntity('timeline_event', e.id)}
                        >
                            <div className="flex items-center justify-between">
                                <span className="text-[11px] text-text-2 group-hover:text-text font-bold truncate leading-tight">{e.title}</span>
                                <Plus size={12} className="text-brand opacity-0 group-hover:opacity-100 transition-all" />
                            </div>
                            <div className="flex items-center gap-1.5 text-[9px] text-text-3 font-bold uppercase tracking-widest opacity-60">
                                <Clock size={8} /> {e.time || 'Point in time'}
                            </div>
                        </div>
                    ))}
                    {timelineEvents.length === 0 && (
                         <div className="text-[10px] text-text-3 italic text-center py-6 border border-dashed border-divider rounded-xl opacity-50">
                            No temporal records
                        </div>
                    )}
               </div>
            </div>
         </div>

         {/* AI Command Strip */}
         <div className="p-4 bg-bg-elev-2 border-t border-border flex flex-col gap-3 shadow-2">
            <div className="flex items-center gap-2 mb-1 ml-1">
                <Wand2 size={12} className="text-brand" />
                <div className="text-[9px] font-black text-text-3 uppercase tracking-[0.3em]">Neural Synthesis</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
                <button className="flex flex-col items-center justify-center gap-1.5 py-3 bg-bg border border-border hover:border-brand/40 hover:bg-hover rounded-xl text-[9px] font-black uppercase tracking-widest text-text-3 hover:text-text transition-all group" data-testid="editor-generate-scene-btn">
                    <Zap size={14} className="group-hover:text-brand transition-colors" />
                    Expand
                </button>
                <button className="flex flex-col items-center justify-center gap-1.5 py-3 bg-bg border border-border hover:border-brand/40 hover:bg-hover rounded-xl text-[9px] font-black uppercase tracking-widest text-text-3 hover:text-text transition-all group" data-testid="editor-rewrite-btn">
                    <Sparkles size={14} className="group-hover:text-brand transition-colors" />
                    Polish
                </button>
            </div>
         </div>
      </aside>
    </div>
  );
};

const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');
