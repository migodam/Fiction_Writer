import React, { useEffect, useState, useRef } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { 
    FileText, Users, Clock, Info, Plus, ChevronDown, 
    ChevronRight, Book, MoreVertical, Search, Zap
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
    <div className="flex h-full overflow-hidden bg-[#121212]">
      {/* Writing Sidebar (Chapters & Scenes) */}
      <div className="w-64 border-r border-[#333333] flex flex-col bg-[#1e1e1e]" data-testid="writing-sidebar">
          <div className="p-4 border-b border-[#333333] flex items-center justify-between">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-[#888888]">Manuscript</h3>
              <button className="p-1 hover:bg-[#333333] rounded text-[#007acc]"><Plus size={14} /></button>
          </div>
          <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
              {chapters.map(chap => (
                  <div key={chap.id} className="mb-1">
                      <div className="px-4 py-1.5 flex items-center gap-2 hover:bg-[#252526] cursor-pointer group transition-colors">
                          <ChevronDown size={12} className="text-[#444444]" />
                          <Book size={12} className="text-[#007acc]" />
                          <span className="text-[11px] font-bold text-[#cccccc] uppercase tracking-tighter">{chap.title}</span>
                      </div>
                      <div className="ml-4 border-l border-[#222222]">
                          {scenes.filter(s => s.chapterId === chap.id).map(scene => (
                              <div 
                                key={scene.id}
                                data-testid={`scene-item-${scene.id}`}
                                className={`px-6 py-2 flex items-center justify-between hover:bg-[#252526] cursor-pointer group transition-colors ${activeSceneId === scene.id ? 'bg-[#252526] border-r-2 border-[#007acc]' : ''}`}
                                onClick={() => setSelectedEntity('scene', scene.id)}
                              >
                                  <span className={`text-[11px] ${activeSceneId === scene.id ? 'text-white font-medium' : 'text-[#666666]'}`}>{scene.title}</span>
                                  <MoreVertical size={10} className="opacity-0 group-hover:opacity-100 text-[#444444]" />
                              </div>
                          ))}
                      </div>
                  </div>
              ))}
          </div>
      </div>

      {/* Editor Main */}
      <div className="flex-1 flex flex-col items-center overflow-y-auto custom-scrollbar bg-[#121212] relative">
        {activeScene ? (
            <div className="w-full max-w-3xl px-10 py-20 min-h-full bg-[#181818] shadow-[0_0_50px_rgba(0,0,0,0.5)] border-x border-[#222222]">
                <input 
                    className="w-full bg-transparent text-4xl font-serif font-bold text-white mb-12 outline-none placeholder-[#222222] tracking-tight"
                    placeholder="Untitled Scene"
                    value={localTitle}
                    onChange={handleTitleChange}
                />
                <div className="flex-1 w-full min-h-[800px] flex flex-col">
                    <textarea 
                        data-testid="writing-editor"
                        className="w-full h-full min-h-[800px] bg-transparent text-lg leading-[1.8] text-[#bbbbbb] outline-none resize-none font-serif placeholder-[#222222]"
                        placeholder="Begin the narrative..."
                        value={localContent}
                        onChange={handleContentChange}
                    />
                </div>
            </div>
        ) : (
            <div className="h-full flex flex-col items-center justify-center text-[#222222]">
                <Zap size={100} className="opacity-5 mb-4" />
                <p className="text-[10px] font-bold uppercase tracking-[0.3em]">No Active Scene</p>
            </div>
        )}
      </div>

      {/* Context Panel (Right) */}
      <aside className="w-72 border-l border-[#333333] bg-[#1e1e1e] flex flex-col" data-testid="context-panel">
         <div className="p-4 border-b border-[#333333] flex items-center justify-between bg-[#252526]">
           <div className="flex items-center gap-2">
                <Search size={14} className="text-[#007acc]" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-[#cccccc]">Narrative Context</span>
           </div>
         </div>
         
         <div className="flex-1 overflow-y-auto custom-scrollbar">
            {/* Characters Section */}
            <div className="p-4 border-b border-[#222222]">
               <div className="flex items-center justify-between mb-4">
                    <h4 className="text-[9px] font-bold text-[#444444] uppercase tracking-widest flex items-center gap-1.5"><Users size={10} /> Personas</h4>
                    <span className="text-[9px] px-1.5 py-0.5 bg-[#252526] rounded text-[#666666]">{characters.length}</span>
               </div>
               <div className="space-y-1">
                    {characters.map(c => (
                        <div 
                            key={c.id} 
                            className="group flex items-center justify-between text-[11px] p-2 hover:bg-[#252526] rounded-md cursor-pointer text-[#888888] hover:text-[#cccccc] transition-all" 
                            data-testid="context-insert-character"
                            onClick={() => setSelectedEntity('character', c.id)}
                        >
                            <span className="truncate">{c.name}</span>
                            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <Plus size={10} className="text-[#007acc]" title="Insert Reference" />
                                <ChevronRight size={10} />
                            </div>
                        </div>
                    ))}
                    {characters.length === 0 && <div className="text-[9px] text-[#333333] italic text-center py-2">No characters found</div>}
               </div>
            </div>

            {/* Timeline Section */}
            <div className="p-4 border-b border-[#222222]">
               <div className="flex items-center justify-between mb-4">
                    <h4 className="text-[9px] font-bold text-[#444444] uppercase tracking-widest flex items-center gap-1.5"><Clock size={10} /> Chronology</h4>
                    <span className="text-[9px] px-1.5 py-0.5 bg-[#252526] rounded text-[#666666]">{timelineEvents.length}</span>
               </div>
               <div className="space-y-1">
                    {timelineEvents.map(e => (
                        <div 
                            key={e.id} 
                            className="group flex flex-col gap-0.5 p-2 hover:bg-[#252526] rounded-md cursor-pointer transition-all border border-transparent hover:border-[#333333]" 
                            data-testid="context-insert-event"
                            onClick={() => setSelectedEntity('timeline_event', e.id)}
                        >
                            <div className="flex items-center justify-between">
                                <span className="text-[11px] text-[#888888] group-hover:text-[#cccccc] font-medium truncate">{e.title}</span>
                                <Plus size={10} className="text-[#007acc] opacity-0 group-hover:opacity-100" />
                            </div>
                            <span className="text-[9px] text-[#444444] group-hover:text-[#666666] uppercase tracking-tighter">{e.time || 'Point in time'}</span>
                        </div>
                    ))}
                    {timelineEvents.length === 0 && <div className="text-[9px] text-[#333333] italic text-center py-2">No events found</div>}
               </div>
            </div>
         </div>

         {/* AI Command Strip */}
         <div className="p-3 bg-[#252526] border-t border-[#333333] flex flex-col gap-2 shadow-2xl">
            <div className="text-[8px] font-bold text-[#444444] uppercase tracking-widest mb-1 ml-1">Intelligent Actions</div>
            <div className="grid grid-cols-2 gap-2">
                <button className="flex items-center justify-center gap-1.5 py-2 bg-[#181818] border border-[#333333] hover:border-[#007acc] rounded text-[9px] font-bold uppercase tracking-widest text-[#666666] hover:text-[#007acc] transition-all" data-testid="editor-generate-scene-btn">
                    <Zap size={10} /> Expand
                </button>
                <button className="flex items-center justify-center gap-1.5 py-2 bg-[#181818] border border-[#333333] hover:border-[#007acc] rounded text-[9px] font-bold uppercase tracking-widest text-[#666666] hover:text-[#007acc] transition-all" data-testid="editor-rewrite-btn">
                    <Zap size={10} /> Polish
                </button>
            </div>
         </div>
      </aside>
    </div>
  );
};

const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');
