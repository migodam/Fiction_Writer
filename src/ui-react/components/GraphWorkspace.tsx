import React, { useMemo, useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { Network, Plus, Maximize2, Minimize2, RefreshCw, Link as LinkIcon, Move, Zap, Database, PanelTopOpen } from 'lucide-react';
import { useI18n } from '../i18n';

const kindStyles: Record<string, string> = {
  free_note: 'bg-amber/10 border-amber/30 text-amber',
  character_ref: 'bg-blue/10 border-blue/30 text-blue',
  event_ref: 'bg-brand/10 border-brand/30 text-brand',
  location_ref: 'bg-green/10 border-green/30 text-green',
  world_item_ref: 'bg-cyan/10 border-cyan/30 text-cyan',
  image_card: 'bg-white/5 border-white/10 text-text-2',
  group_frame: 'bg-transparent border-dashed border-border text-text-3',
};

export const GraphWorkspace = () => {
  const { graphBoards, activeGraphBoardId, selectedEntity, setSelectedEntity, addGraphSyncProposal } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const [zoom, setZoom] = useState(1);
  const [isAutoLayoutRunning, setIsAutoLayoutRunning] = useState(false);

  const board = useMemo(() => graphBoards.find((entry) => entry.id === activeGraphBoardId) || graphBoards[0], [activeGraphBoardId, graphBoards]);

  const handleAutoLayout = () => {
    setIsAutoLayoutRunning(true);
    setTimeout(() => {
      setIsAutoLayoutRunning(false);
      setLastActionStatus('Layout updated');
    }, 800);
  };

  const handleQueueSync = () => {
    const selectedNode = board?.nodes.find((node) => node.linkedEntityId === selectedEntity.id || node.id === selectedEntity.id);
    addGraphSyncProposal(
      'Graph sync batch',
      selectedNode
        ? `Queue sync for ${selectedNode.label} and convert it into reviewed project updates.`
        : 'Queue sync for the current graph selection and send it into Workbench Inbox.'
    );
    setLastActionStatus('Proposal queued');
  };

  return (
    <div className="flex flex-col h-full bg-bg overflow-hidden animate-in fade-in duration-500">
      <div className="h-12 border-b border-border flex items-center px-6 gap-8 bg-bg-elev-1 z-10 shadow-1" data-testid="graph-toolbar">
        <div className="flex items-center gap-3">
          <button data-testid="graph-add-node-btn" className="flex items-center gap-2 px-4 py-1.5 bg-brand hover:bg-brand-2 text-white text-[11px] font-bold rounded-lg shadow-2 transition-all uppercase tracking-widest active:scale-95"><Plus size={14} strokeWidth={3} /> {t('graph.addNode')}</button>
          <button data-testid="graph-add-edge-btn" className="flex items-center gap-2 px-4 py-1.5 bg-bg-elev-2 border border-border hover:border-brand-2 text-text-2 hover:text-text text-[11px] font-bold rounded-lg transition-all uppercase tracking-widest active:scale-95"><LinkIcon size={14} /> {t('graph.addEdge')}</button>
        </div>
        <div className="h-5 w-px bg-divider"></div>
        <div className="flex items-center gap-4">
          <button data-testid="graph-auto-layout-btn" className={`flex items-center gap-2 px-3 py-1.5 bg-bg border border-border rounded-lg text-text-3 hover:text-brand transition-all active:scale-95 ${isAutoLayoutRunning ? 'opacity-50 pointer-events-none' : ''}`} onClick={handleAutoLayout}><RefreshCw size={14} className={isAutoLayoutRunning ? 'animate-spin' : ''} /><span className="text-[10px] font-bold uppercase tracking-widest">{t('graph.autoLayout')}</span></button>
          <button data-testid="graph-reset-layout-btn" className="flex items-center gap-2 px-3 py-1.5 bg-bg border border-border rounded-lg text-text-3 hover:text-brand transition-all active:scale-95" onClick={() => setLastActionStatus('Layout reset')}><Move size={14} /><span className="text-[10px] font-bold uppercase tracking-widest">{t('graph.reset')}</span></button>
          <button data-testid="graph-sync-selection-btn" className="flex items-center gap-2 px-3 py-1.5 bg-bg border border-border rounded-lg text-text-3 hover:text-brand transition-all active:scale-95" onClick={handleQueueSync}><Database size={14} /><span className="text-[10px] font-bold uppercase tracking-widest">{t('graph.queueSync')}</span></button>
        </div>
        <div className="ml-auto flex items-center gap-4 bg-bg border border-border rounded-lg px-4 py-1.5 shadow-inner">
          <button className="text-text-3 hover:text-brand" onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}><Minimize2 size={14} /></button>
          <input type="range" min="0.5" max="2" step="0.1" value={zoom} onChange={(event) => setZoom(parseFloat(event.target.value))} className="w-24 h-1 bg-divider rounded-lg appearance-none cursor-pointer accent-brand" />
          <button className="text-text-3 hover:text-brand" onClick={() => setZoom(Math.min(2, zoom + 0.1))}><Maximize2 size={14} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-bg relative custom-scrollbar cursor-grab active:cursor-grabbing" data-testid="graph-canvas">
        <div className="absolute inset-0 pointer-events-none opacity-[0.03]" style={{ backgroundImage: `radial-gradient(var(--text) 1px, transparent 1px)`, backgroundSize: `${50 * zoom}px ${50 * zoom}px` }}></div>
        <div className="relative min-h-full p-12" style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
          {board?.nodes.map((node) => {
            const isSelected = selectedEntity.id === node.linkedEntityId || selectedEntity.id === node.id;
            const icon = node.kind === 'image_card' ? <PanelTopOpen size={18} /> : <Network size={18} />;
            return (
              <button
                type="button"
                key={node.id}
                data-testid={`graph-node-${node.linkedEntityId || node.id}`}
                className={`absolute rounded-2xl border-2 p-4 text-left shadow-2 transition-all ${kindStyles[node.kind]} ${isSelected ? 'ring-2 ring-brand/40' : ''}`}
                style={{ left: node.x, top: node.y, width: node.width, minHeight: node.height }}
                onClick={() => setSelectedEntity((node.linkedEntityType || 'graph_node') as any, node.linkedEntityId || node.id)}
              >
                {node.kind === 'image_card' && node.imageAssetId ? (
                  <img src={node.imageAssetId} alt={node.label} className="mb-3 h-24 w-full rounded-xl object-cover" />
                ) : null}
                <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.25em] opacity-80">{icon}<span>{node.kind}</span></div>
                <div className="text-sm font-black text-text">{node.label}</div>
                <div className="mt-2 text-xs leading-relaxed text-text-2">{node.description}</div>
                {isSelected && <div className="absolute -top-2 -right-2 bg-brand text-white p-1 rounded-full shadow-lg border border-white/20"><Zap size={10} /></div>}
              </button>
            );
          })}
          {!board?.nodes.length && (
            <div className="col-span-4 py-40 flex flex-col items-center justify-center text-text-3 opacity-20">
              <Network size={80} className="mb-6 animate-pulse" />
              <p className="text-sm font-black uppercase tracking-[0.4em]">{t('graph.empty')}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
