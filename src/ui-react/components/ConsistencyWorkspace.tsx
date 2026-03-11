import React, { useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { 
    CheckCircle, AlertTriangle, AlertCircle, RefreshCw, 
    ChevronRight, Filter, ExternalLink, ArrowRight,
    Search, ShieldCheck, Zap
} from 'lucide-react';

export const ConsistencyWorkspace = () => {
  const { setLastActionStatus } = useUIStore();
  
  const [isRunning, setIsRunning] = useState(false);
  const [issues, setIssues] = useState<any[]>([]);

  const handleRunCheck = () => {
    setIsRunning(true);
    setIssues([]);
    setTimeout(() => {
        setIsRunning(false);
        setIssues([
            { id: 'iss_1', type: 'timeline', severity: 'high', title: 'Temporal Paradox', description: 'Alice is in London and Paris at the same time in Chapter 3.', suggestion: "Move Alice's arrival to later in the day." },
            { id: 'iss_2', type: 'character', severity: 'medium', title: 'Trait Violation', description: 'Bob is described as a coward but fights a dragon without hesitation.', suggestion: 'Add a moment of internal conflict or fear.' },
            { id: 'iss_3', type: 'world', severity: 'low', title: 'Resource Inconsistency', description: 'The ancient relic was destroyed but reappears in the background.', suggestion: 'Replace relic with a regular sword in scene 4.' },
        ]);
        setLastActionStatus('Consistency check complete');
    }, 1500);
  };

  return (
    <div className="flex flex-col h-full bg-bg animate-in fade-in duration-500">
      {/* Consistency Toolbar */}
      <div className="h-14 border-b border-border flex items-center px-8 gap-8 bg-bg-elev-1 z-10 shadow-1" data-testid="consistency-toolbar">
        <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-brand/10 border border-brand/20 flex items-center justify-center text-brand">
                <ShieldCheck size={20} />
            </div>
            <h2 className="text-sm font-black text-text uppercase tracking-[0.2em]">Continuity Sentinel</h2>
        </div>

        <div className="h-6 w-px bg-divider mx-2"></div>

        <button 
            data-testid="run-consistency-btn"
            className={`px-6 py-2 bg-brand hover:bg-brand-2 text-white font-black rounded-lg text-[10px] uppercase tracking-widest shadow-2 active:scale-95 transition-all flex items-center gap-2 ${isRunning ? 'opacity-50 pointer-events-none' : ''}`}
            onClick={handleRunCheck}
        >
            <RefreshCw size={14} className={isRunning ? 'animate-spin' : ''} />
            {isRunning ? 'Auditing...' : 'Run Full Audit'}
        </button>

        <div className="ml-auto flex items-center gap-6">
            <FilterChip label="All Issues" count={issues.length} active />
            <FilterChip label="High" count={issues.filter(i => i.severity === 'high').length} color="text-red" />
            <FilterChip label="Medium" count={issues.filter(i => i.severity === 'medium').length} color="text-amber" />
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto custom-scrollbar bg-bg p-12">
        {issues.length > 0 ? (
            <div className="max-w-5xl mx-auto space-y-6">
                {issues.map(issue => (
                    <div 
                        key={issue.id}
                        className="bg-bg-elev-1 border border-border rounded-2xl p-6 flex items-start gap-6 hover:border-brand/40 transition-all group shadow-sm"
                        data-testid="consistency-issue-item"
                    >
                        <div className={`mt-1 p-2 rounded-lg ${
                            issue.severity === 'high' ? 'bg-red/10 text-red' : 
                            issue.severity === 'medium' ? 'bg-amber/10 text-amber' : 'bg-blue/10 text-blue'
                        }`}>
                            {issue.severity === 'high' ? <AlertCircle size={20} /> : <AlertTriangle size={20} />}
                        </div>
                        <div className="flex-1">
                            <div className="flex items-center justify-between mb-2">
                                <h3 className="text-lg font-black text-text group-hover:text-brand transition-colors">{issue.title}</h3>
                                <span className={`text-[9px] font-black uppercase tracking-[0.2em] px-2 py-0.5 rounded-full border ${
                                    issue.severity === 'high' ? 'border-red/30 text-red bg-red/5' : 
                                    issue.severity === 'medium' ? 'border-amber/30 text-amber bg-amber/5' : 'border-blue/30 text-blue bg-blue/5'
                                }`}>{issue.severity} priority</span>
                            </div>
                            <p className="text-sm text-text-2 mb-6 leading-relaxed opacity-80">{issue.description}</p>
                            
                            <div className="bg-bg rounded-xl border border-divider p-4 flex items-center justify-between group/fix hover:border-brand/30 transition-all">
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-lg bg-green/10 flex items-center justify-center text-green">
                                        <Zap size={14} />
                                    </div>
                                    <div>
                                        <span className="text-[9px] font-black uppercase tracking-widest text-text-3 block mb-0.5">Proposed Resolution</span>
                                        <span className="text-[11px] font-bold text-text-2">{issue.suggestion}</span>
                                    </div>
                                </div>
                                <button className="p-2 text-brand opacity-0 group-hover/fix:opacity-100 transition-all translate-x-2 group-hover/fix:translate-x-0 flex items-center gap-2 text-[10px] font-black uppercase tracking-widest">
                                    Apply Fix <ArrowRight size={14} />
                                </button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        ) : !isRunning ? (
            <div className="h-full flex flex-col items-center justify-center text-text-3 select-none opacity-40">
                <CheckCircle size={100} className="mb-8" />
                <p className="text-[11px] font-black uppercase tracking-[0.5em]">No Disruptions Detected</p>
                <p className="text-[9px] mt-4 uppercase tracking-widest font-medium">Run the continuity sentinel to identify narrative conflicts</p>
            </div>
        ) : (
            <div className="h-full flex flex-col items-center justify-center text-brand select-none">
                <div className="relative mb-8">
                    <ShieldCheck size={100} className="animate-pulse" />
                    <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-24 h-24 rounded-full border-2 border-brand border-t-transparent animate-spin"></div>
                    </div>
                </div>
                <p className="text-[11px] font-black uppercase tracking-[0.5em]">Auditing Manuscript</p>
                <p className="text-[9px] mt-4 text-text-3 uppercase tracking-widest font-medium animate-bounce">Scanning temporal nodes...</p>
            </div>
        )}
      </div>
    </div>
  );
};

const FilterChip = ({ label, count, active, color = 'text-text-3' }: { label: string, count: number, active?: boolean, color?: string }) => (
    <div className={`flex items-center gap-2 px-3 py-1 rounded-full border transition-all cursor-pointer ${
        active ? 'bg-bg-elev-2 border-brand text-brand' : 'border-divider text-text-3 hover:border-text-3'
    }`}>
        <span className="text-[10px] font-black uppercase tracking-widest">{label}</span>
        <span className={`text-[9px] font-bold px-1.5 rounded-full bg-bg ${color} border border-divider`}>{count}</span>
    </div>
);
