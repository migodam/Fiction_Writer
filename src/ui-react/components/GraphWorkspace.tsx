import React, { useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { 
    Network, Share2, Plus, Maximize2, Minimize2, 
    RefreshCw, Trash2, Link as LinkIcon, Move, 
    Layers, Zap, Database
} from 'lucide-react';

export const GraphWorkspace = () => {
  const { 
      characters, timelineEvents, relationships, 
      selectedEntity, setSelectedEntity, 
      addRelationship, deleteRelationship 
  } = useProjectStore();
  const { setLastActionStatus, sidebarSection } = useUIStore();
  
  const [zoom, setZoom] = useState(1);
  const [isAutoLayoutRunning, setIsAutoLayoutRunning] = useState(false);

  const handleAutoLayout = () => {
    setIsAutoLayoutRunning(true);
    setTimeout(() => {
        setIsAutoLayoutRunning(false);
        setLastActionStatus('Layout updated');
    }, 800);
  };

  const handleResetLayout = () => {
    setLastActionStatus('Layout reset');
  };

  const nodeTypes = [
    { id: 'character', label: 'Characters', icon: <Users size={14} />, color: 'text-blue' },
    { id: 'event', label: 'Events', icon: <Clock size={14} />, color: 'text-amber' },
    { id: 'location', label: 'Locations', icon: <MapPin size={14} />, color: 'text-green' },
  ];

  // Combined node list for visualization
  const allNodes = [
    ...characters.map(c => ({ id: c.id, label: c.name, type: 'character' })),
    ...timelineEvents.map(e => ({ id: e.id, label: e.title, type: 'event' })),
  ];

  return (
    <div className="flex flex-col h-full bg-bg overflow-hidden animate-in fade-in duration-500">
      {/* Graph Toolbar */}
      <div className="h-12 border-b border-border flex items-center px-6 gap-8 bg-bg-elev-1 z-10 shadow-1" data-testid="graph-toolbar">
        <div className="flex items-center gap-3">
            <button 
                data-testid="graph-add-node-btn"
                className="flex items-center gap-2 px-4 py-1.5 bg-brand hover:bg-brand-2 text-white text-[11px] font-bold rounded-lg shadow-2 transition-all uppercase tracking-widest active:scale-95"
            >
                <Plus size={14} strokeWidth={3} /> Add Node
            </button>
            <button 
                data-testid="graph-add-edge-btn"
                className="flex items-center gap-2 px-4 py-1.5 bg-bg-elev-2 border border-border hover:border-brand-2 text-text-2 hover:text-text text-[11px] font-bold rounded-lg transition-all uppercase tracking-widest active:scale-95"
            >
                <LinkIcon size={14} /> Add Edge
            </button>
        </div>

        <div className="h-5 w-px bg-divider"></div>

        <div className="flex items-center gap-4">
            <button 
                data-testid="graph-auto-layout-btn"
                className={`flex items-center gap-2 px-3 py-1.5 bg-bg border border-border rounded-lg text-text-3 hover:text-brand transition-all active:scale-95 ${isAutoLayoutRunning ? 'opacity-50 pointer-events-none' : ''}`}
                onClick={handleAutoLayout}
                title="Auto Layout"
            >
                <RefreshCw size={14} className={isAutoLayoutRunning ? 'animate-spin' : ''} />
                <span className="text-[10px] font-bold uppercase tracking-widest">Auto Layout</span>
            </button>
            <button 
                data-testid="graph-reset-layout-btn"
                className="flex items-center gap-2 px-3 py-1.5 bg-bg border border-border rounded-lg text-text-3 hover:text-brand transition-all active:scale-95"
                onClick={handleResetLayout}
                title="Reset Layout"
            >
                <Move size={14} />
                <span className="text-[10px] font-bold uppercase tracking-widest">Reset</span>
            </button>
        </div>

        <div className="h-5 w-px bg-divider"></div>

        <div className="flex items-center gap-4 bg-bg border border-border rounded-lg px-4 py-1.5 shadow-inner">
            <button className="text-text-3 hover:text-brand" onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}><Minimize2 size={14} /></button>
            <input 
                type="range" 
                min="0.5" max="2" step="0.1" value={zoom} 
                onChange={(e) => setZoom(parseFloat(e.target.value))}
                className="w-24 h-1 bg-divider rounded-lg appearance-none cursor-pointer accent-brand"
            />
            <button className="text-text-3 hover:text-brand" onClick={() => setZoom(Math.min(2, zoom + 0.1))}><Maximize2 size={14} /></button>
        </div>

        <div className="ml-auto flex items-center gap-6 opacity-40">
            <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue"></div>
                <span className="text-[9px] font-black uppercase tracking-widest">Character</span>
            </div>
            <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-amber"></div>
                <span className="text-[9px] font-black uppercase tracking-widest">Event</span>
            </div>
        </div>
      </div>

      {/* Graph Canvas */}
      <div 
        className="flex-1 overflow-hidden bg-bg relative custom-scrollbar cursor-grab active:cursor-grabbing" 
        data-testid="graph-canvas"
      >
        {/* Background Grid */}
        <div className="absolute inset-0 pointer-events-none opacity-[0.03]" style={{ 
            backgroundImage: `radial-gradient(var(--text) 1px, transparent 1px)`,
            backgroundSize: `${50 * zoom}px ${50 * zoom}px`
        }}></div>

        <div 
            className="absolute inset-0 flex items-center justify-center p-20"
            style={{ transform: `scale(${zoom})` }}
        >
            <div className="relative w-full h-full">
                {/* SVG for Edges */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none overflow-visible">
                    <defs>
                        <marker id="arrow" viewBox="0 0 10 10" refX="25" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--divider)" />
                        </marker>
                    </defs>
                    {relationships.map(rel => {
                        // Dummy lines since we don't have absolute positions in this mock view
                        return null; 
                    })}
                </svg>

                {/* Nodes Visualization - Simple Grid for now */}
                <div className="grid grid-cols-4 gap-12 max-w-5xl mx-auto">
                    {allNodes.map((node, idx) => {
                        const isSelected = selectedEntity.id === node.id;
                        return (
                            <div 
                                key={node.id}
                                data-testid={`graph-node-${node.id}`}
                                className={`w-44 p-4 rounded-xl border-2 transition-all cursor-pointer group shadow-2 flex flex-col items-center text-center ${
                                    isSelected 
                                    ? 'bg-bg-elev-2 border-brand ring-4 ring-brand/10' 
                                    : 'bg-bg-elev-1 border-border hover:border-brand/40 hover:bg-bg-elev-2'
                                }`}
                                onClick={() => setSelectedEntity(node.type as any, node.id)}
                            >
                                <div className={`w-12 h-12 rounded-full flex items-center justify-center mb-3 border border-divider shadow-inner group-hover:scale-110 transition-transform ${
                                    node.type === 'character' ? 'bg-blue/10 text-blue' : 'bg-amber/10 text-amber'
                                }`}>
                                    {node.type === 'character' ? <User size={20} /> : <Clock size={20} />}
                                </div>
                                <div className="text-xs font-black text-text uppercase tracking-widest truncate w-full group-hover:text-brand transition-colors">{node.label}</div>
                                <div className="text-[9px] text-text-3 font-bold uppercase tracking-[0.2em] mt-1 opacity-60">{node.type}</div>
                                
                                {isSelected && (
                                    <div className="absolute -top-2 -right-2 bg-brand text-white p-1 rounded-full shadow-lg border border-white/20">
                                        <Zap size={10} />
                                    </div>
                                )}
                            </div>
                        );
                    })}
                    {allNodes.length === 0 && (
                        <div className="col-span-4 py-40 flex flex-col items-center justify-center text-text-3 opacity-20">
                            <Network size={80} className="mb-6 animate-pulse" />
                            <p className="text-sm font-black uppercase tracking-[0.4em]">Narrative Cluster Empty</p>
                        </div>
                    )}
                </div>
            </div>
        </div>

        {/* Floating Mini Map Placeholder */}
        <div className="absolute bottom-8 right-8 w-48 h-32 bg-bg-elev-2 border border-border rounded-xl shadow-2 p-2 opacity-50 hover:opacity-100 transition-opacity">
            <div className="w-full h-full border border-divider rounded-md flex items-center justify-center">
                <span className="text-[8px] font-black uppercase tracking-widest text-text-3">Mini Map</span>
            </div>
        </div>
      </div>
    </div>
  );
};

import { User, Clock, MapPin, Users } from 'lucide-react';
