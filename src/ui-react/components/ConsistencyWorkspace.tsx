import React, { useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { AlertTriangle, AlertCircle, RefreshCw, ArrowRight, ShieldCheck, Zap } from 'lucide-react';
import { useI18n } from '../i18n';

export const ConsistencyWorkspace = () => {
  const { issues, addProposal, setSelectedEntity } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const [isRunning, setIsRunning] = useState(false);

  const handleRunCheck = () => {
    setIsRunning(true);
    setTimeout(() => {
      setIsRunning(false);
      setLastActionStatus('Consistency check complete');
    }, 1200);
  };

  const queueFix = (issueId: string) => {
    const issue = issues.find((entry) => entry.id === issueId);
    if (!issue) {
      return;
    }
    addProposal({
      id: `proposal_fix_${issue.id}_${Date.now()}`,
      title: `Fix: ${issue.title}`,
      source: 'consistency',
      description: issue.description,
      targetEntityType: 'issue',
      targetEntityId: issue.id,
      preview: issue.fixSuggestion || 'Review and resolve the reported inconsistency.',
      status: 'pending',
      createdAt: new Date().toISOString(),
    });
    setSelectedEntity('issue', issue.id);
    setLastActionStatus('Proposal queued');
  };

  return (
    <div className="flex flex-col h-full bg-bg animate-in fade-in duration-500">
      <div className="h-14 border-b border-border flex items-center px-8 gap-8 bg-bg-elev-1 z-10 shadow-1" data-testid="consistency-toolbar">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-brand/10 border border-brand/20 flex items-center justify-center text-brand"><ShieldCheck size={20} /></div>
          <h2 className="text-sm font-black text-text uppercase tracking-[0.2em]">{t('consistency.title')}</h2>
        </div>
        <button data-testid="run-consistency-btn" className={`px-6 py-2 bg-brand hover:bg-brand-2 text-white font-black rounded-lg text-[10px] uppercase tracking-widest shadow-2 transition-all flex items-center gap-2 ${isRunning ? 'opacity-50 pointer-events-none' : ''}`} onClick={handleRunCheck}>
          <RefreshCw size={14} className={isRunning ? 'animate-spin' : ''} />
          {isRunning ? 'Auditing...' : t('consistency.run')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar bg-bg p-12">
        {issues.length > 0 ? (
          <div className="max-w-5xl mx-auto space-y-6">
            {issues.map((issue) => (
              <div key={issue.id} className="bg-bg-elev-1 border border-border rounded-2xl p-6 flex items-start gap-6 hover:border-brand/40 transition-all group shadow-sm" data-testid="consistency-issue-item">
                <div className={`${issue.severity === 'high' ? 'bg-red/10 text-red' : issue.severity === 'medium' ? 'bg-amber/10 text-amber' : 'bg-blue/10 text-blue'} mt-1 p-2 rounded-lg`}>
                  {issue.severity === 'high' ? <AlertCircle size={20} /> : <AlertTriangle size={20} />}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-lg font-black text-text">{issue.title}</h3>
                    <span className="text-[9px] font-black uppercase tracking-[0.2em] px-2 py-0.5 rounded-full border border-border text-text-3">{issue.severity}</span>
                  </div>
                  <p className="text-sm text-text-2 mb-6 leading-relaxed opacity-80">{issue.description}</p>
                  <div className="rounded-xl border border-divider bg-bg p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-green/10 flex items-center justify-center text-green"><Zap size={14} /></div>
                      <div>
                        <span className="text-[9px] font-black uppercase tracking-widest text-text-3 block mb-0.5">Proposed Resolution</span>
                        <span className="text-[11px] font-bold text-text-2">{issue.fixSuggestion}</span>
                      </div>
                    </div>
                    <button className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-brand" onClick={() => queueFix(issue.id)} data-testid="consistency-queue-fix-btn">
                      Queue Fix <ArrowRight size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : !isRunning ? (
          <div className="h-full flex flex-col items-center justify-center text-text-3 select-none opacity-40">
            <ShieldCheck size={100} className="mb-8" />
            <p className="text-[11px] font-black uppercase tracking-[0.5em]">{t('consistency.none')}</p>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-brand select-none">
            <ShieldCheck size={100} className="animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
};
