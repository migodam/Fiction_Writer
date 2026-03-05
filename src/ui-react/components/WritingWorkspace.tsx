import React, { useEffect, useState, useRef } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { FileText, Users, Clock, Info } from 'lucide-react';

export const WritingWorkspace = () => {
  const { currentSceneContent, setCurrentSceneContent, characters, timelineEvents } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  
  const [localContent, setLocalContent] = useState(currentSceneContent);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setLocalContent(val);
    
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    
    saveTimeoutRef.current = setTimeout(() => {
      setCurrentSceneContent(val);
      setLastActionStatus('Saved');
    }, 1000); // 1s debounce
  };

  useEffect(() => {
    return () => {
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    };
  }, []);

  return (
    <div className="flex h-full overflow-hidden bg-[#121212]">
      {/* Editor Main */}
      <div className="flex-1 flex flex-col items-center overflow-y-auto">
        <div className="w-full max-w-4xl p-16 min-h-full bg-[#1e1e1e] shadow-2xl border-x border-[#333333]">
           <input 
             className="w-full bg-transparent text-4xl font-serif font-bold text-[#cccccc] mb-8 outline-none placeholder-[#333333]"
             placeholder="Scene Title..."
             defaultValue="Chapter 1: The Beginning"
           />
           <textarea 
             data-testid="writing-editor"
             className="w-full flex-1 bg-transparent text-lg leading-relaxed text-[#cccccc] outline-none resize-none font-serif min-h-[80vh]"
             placeholder="Once upon a time..."
             value={localContent}
             onChange={handleTextChange}
           />
        </div>
      </div>

      {/* Context Panel (Right) */}
      <aside className="w-72 border-l border-[#333333] bg-[#252526] flex flex-col" data-testid="context-panel">
         <div className="p-4 border-b border-[#333333] flex items-center gap-2">
           <Info size={16} className="text-[#007acc]" />
           <span className="text-xs font-bold uppercase tracking-wider">Context Panel</span>
         </div>
         
         <div className="flex-1 overflow-y-auto">
            {/* Characters in Scene */}
            <div className="p-4 border-b border-[#333333]">
               <h4 className="text-[10px] font-bold text-[#666666] uppercase mb-2 flex items-center gap-1"><Users size={10} /> Characters</h4>
               {characters.length === 0 ? (
                 <div className="text-[10px] text-[#444444] italic">No characters referenced</div>
               ) : (
                 <div className="space-y-1">
                    {characters.map(c => (
                        <div key={c.id} className="text-xs p-1.5 hover:bg-[#333333] rounded cursor-pointer text-[#cccccc]" data-testid="context-insert-character">{c.name}</div>
                    ))}
                 </div>
               )}
            </div>

            {/* Timeline References */}
            <div className="p-4 border-b border-[#333333]">
               <h4 className="text-[10px] font-bold text-[#666666] uppercase mb-2 flex items-center gap-1"><Clock size={10} /> Timeline</h4>
               {timelineEvents.length === 0 ? (
                 <div className="text-[10px] text-[#444444] italic">No events linked</div>
               ) : (
                 <div className="space-y-1">
                    {timelineEvents.map(e => (
                        <div key={e.id} className="text-xs p-1.5 hover:bg-[#333333] rounded cursor-pointer text-[#cccccc]" data-testid="context-insert-event">{e.title}</div>
                    ))}
                 </div>
               )}
            </div>
         </div>

         {/* AI Toolbar stub */}
         <div className="p-2 border-t border-[#333333] grid grid-cols-2 gap-2">
            <button className="text-[10px] p-2 bg-[#333333] hover:bg-[#444444] rounded uppercase font-bold text-[#888888]" data-testid="editor-generate-scene-btn">Generate</button>
            <button className="text-[10px] p-2 bg-[#333333] hover:bg-[#444444] rounded uppercase font-bold text-[#888888]" data-testid="editor-rewrite-btn">Rewrite</button>
         </div>
      </aside>
    </div>
  );
};
