import React, { useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { 
    PlayCircle, Sparkles, ChevronRight, Zap, 
    History, Plus, Trash2, Save, Terminal,
    Activity, Brain, Microscope, FastForward
} from 'lucide-react';

export const SimulationWorkspace = () => {
  const { characters, timelineEvents } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  
  const [activeScenario, setActiveScenario] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const scenarios = [
    { id: 'scen_1', name: 'Betrayal at Dawn', description: 'What if Alice betrays Bob before the meeting?' },
    { id: 'scen_2', name: 'Lost Artifact', description: 'What if the ancient relic is destroyed in Chapter 2?' },
  ];

  const handleRunSimulation = () => {
    setIsRunning(true);
    setTimeout(() => {
        setIsRunning(false);
        setLastActionStatus('Simulation complete');
    }, 2000);
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      {/* Left: Scenarios List */}
      <div className="w-72 border-r border-border flex flex-col bg-bg-elev-1 shadow-1" data-testid="simulation-scenario-list">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('simulation.scenarios')}</h3>
            <button 
                className="p-1 hover:bg-hover rounded-lg text-brand transition-colors"
                title="New Scenario"
            >
                <Plus size={16} />
            </button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
            {scenarios.map(scen => (
                <div 
                    key={scen.id}
                    className={`px-4 py-3 rounded-xl cursor-pointer transition-all group relative ${
                        activeScenario === scen.id ? 'bg-active text-text shadow-sm' : 'text-text-3 hover:bg-hover'
                    }`}
                    onClick={() => setActiveScenario(scen.id)}
                >
                    <div className="flex items-center gap-3 mb-1">
                        <PlayCircle size={14} className={activeScenario === scen.id ? 'text-brand' : 'opacity-40'} />
                        <span className="text-[11px] font-black uppercase tracking-widest truncate">{scen.name}</span>
                    </div>
                    <p className="text-[10px] opacity-60 line-clamp-1 ml-6 font-medium">{scen.description}</p>
                </div>
            ))}
        </div>
      </div>

      {/* Main Simulation View */}
      <div className="flex-1 flex flex-col bg-bg overflow-y-auto custom-scrollbar p-12">
        {activeScenario ? (
            <div className="max-w-4xl mx-auto w-full animate-in fade-in duration-500">
                <div className="flex items-center justify-between mb-12">
                    <div className="flex items-center gap-4">
                        <div className="w-14 h-14 rounded-2xl bg-brand/10 border border-brand/20 flex items-center justify-center text-brand shadow-inner">
                            <Brain size={28} />
                        </div>
                        <div>
                            <h2 className="text-2xl font-black text-text uppercase tracking-tight">{t('simulation.title')}</h2>
                            <p className="text-[10px] font-bold text-text-3 uppercase tracking-[0.3em] mt-1">{t('simulation.subtitle')}</p>
                        </div>
                    </div>
                    <button 
                        data-testid="run-simulation-btn"
                        className={`px-8 py-3 bg-brand hover:bg-brand-2 text-white font-black rounded-xl text-[11px] uppercase tracking-widest shadow-2 active:scale-95 transition-all flex items-center gap-2.5 ring-1 ring-white/10 ${isRunning ? 'opacity-50 pointer-events-none' : ''}`}
                        onClick={handleRunSimulation}
                    >
                        {isRunning ? <FastForward size={16} className="animate-spin" /> : <Zap size={16} />}
                        {isRunning ? 'Synthesizing...' : t('simulation.execute')}
                    </button>
                </div>

                {/* Configuration Grid */}
                <div className="grid grid-cols-2 gap-8 mb-12">
                    <div className="p-6 bg-bg-elev-1 border border-border rounded-2xl shadow-1">
                        <h4 className="text-[10px] font-black text-text-3 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                            <Microscope size={12} className="text-brand" /> {t('simulation.variables')}
                        </h4>
                        <div className="space-y-4">
                            <VariableRow label="Character Agency" value="High" />
                            <VariableRow label="Plot Determinism" value="Low" />
                            <VariableRow label="Chaos Factor" value="0.42" />
                        </div>
                    </div>
                    <div className="p-6 bg-bg-elev-1 border border-border rounded-2xl shadow-1">
                        <h4 className="text-[10px] font-black text-text-3 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                            <History size={12} className="text-amber" /> {t('simulation.anchors')}
                        </h4>
                        <div className="space-y-4">
                            <VariableRow label="Timeline Start" value="Event A" />
                            <VariableRow label="Locked Facts" value="3 Detected" />
                            <VariableRow label="Simulation Depth" value="Short" />
                        </div>
                    </div>
                </div>

                {/* Simulation Output Area */}
                <div className="bg-bg-elev-2 border border-border rounded-3xl p-1 overflow-hidden shadow-2">
                    <div className="h-10 border-b border-border bg-bg-elev-1 flex items-center px-6 justify-between">
                        <div className="flex items-center gap-2">
                            <Terminal size={12} className="text-text-3" />
                            <span className="text-[9px] font-black uppercase tracking-[0.3em] text-text-3">{t('simulation.console')}</span>
                        </div>
                        <div className="flex gap-1.5">
                            <div className="w-2 h-2 rounded-full bg-red/20"></div>
                            <div className="w-2 h-2 rounded-full bg-amber/20"></div>
                            <div className="w-2 h-2 rounded-full bg-green/20"></div>
                        </div>
                    </div>
                    <div className="p-8 min-h-[400px] bg-bg font-mono text-[11px] text-text-2 space-y-4 leading-relaxed custom-scrollbar">
                        {isRunning ? (
                            <div className="space-y-2 animate-pulse">
                                <p className="text-brand">[SYSTEM] Initializing narrative shards...</p>
                                <p>[SYSTEM] Resolving character motivations for Alice...</p>
                                <p>[SYSTEM] Calculating world model impact...</p>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                <p className="text-text-3 opacity-40 italic font-sans py-20 text-center uppercase tracking-widest text-[9px]">{t('simulation.awaiting')}</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        ) : (
            <div className="h-full flex flex-col items-center justify-center text-text-3 select-none">
                <Activity size={120} className="opacity-5 mb-8" />
                <p className="text-[11px] font-black uppercase tracking-[0.5em] opacity-40">Narrative Laboratory</p>
                <p className="text-[9px] mt-4 opacity-20 uppercase tracking-widest font-medium">{t('simulation.awaitingBody')}</p>
            </div>
        )}
      </div>
    </div>
  );
};

const VariableRow = ({ label, value }: { label: string, value: string }) => (
    <div className="flex items-center justify-between py-2 border-b border-divider last:border-0">
        <span className="text-[10px] font-bold text-text-2">{label}</span>
        <span className="text-[10px] font-black text-brand uppercase tracking-tighter bg-brand/5 px-2 py-0.5 rounded border border-brand/10">{value}</span>
    </div>
);
