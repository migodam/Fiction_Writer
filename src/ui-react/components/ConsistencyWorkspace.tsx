import React, { useMemo, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, EyeOff, RefreshCw, Wrench } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import { useI18n } from '../i18n';

export const ConsistencyWorkspace = () => {
  const { issues, addProposal, resolveIssue, dismissIssue, setSelectedEntity, runConsistencyCheck, w4Status, projectRoot, selectedEntity } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { locale } = useI18n();
  const zh = locale === 'zh-CN';
  const [filter, setFilter] = useState<'open' | 'resolved' | 'ignored' | 'all'>('open');
  const isRunning = w4Status === 'running';

  const visibleIssues = useMemo(
    () =>
      issues.filter((issue) => {
        if (filter === 'all') return issue.visibility !== 'hidden';
        if (filter === 'open') return issue.status === 'open' && issue.visibility !== 'hidden';
        return issue.status === filter;
      }),
    [filter, issues],
  );

  const queueFix = (issueId: string) => {
    const issue = issues.find((entry) => entry.id === issueId);
    if (!issue) return;
    addProposal({
      id: `proposal_fix_${issue.id}_${Date.now()}`,
      title: `${zh ? '修复' : 'Fix'}: ${issue.title}`,
      source: 'consistency',
      kind: 'qa_fix',
      description: issue.description,
      targetEntityType: 'issue',
      targetEntityId: issue.id,
      preview: issue.fixSuggestion || (zh ? '请审阅并修复这个一致性问题。' : 'Review and resolve this consistency issue.'),
      originIssueId: issue.id,
      reviewPolicy: 'manual_workbench',
      status: 'pending',
      createdAt: new Date().toISOString(),
    });
    setSelectedEntity('issue', issue.id);
    setLastActionStatus(zh ? '已加入修复提案' : 'Fix proposal queued');
  };

  return (
    <div className="flex h-full flex-col bg-bg">
      <div className="flex items-center justify-between border-b border-border bg-bg-elev-1 px-8 py-4" data-testid="consistency-toolbar">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '一致性' : 'Consistency'}</div>
          <div className="mt-1 text-xl font-black text-text">{zh ? '叙事审计中心' : 'Narrative Audit Center'}</div>
        </div>
        <div className="flex items-center gap-3">
          {(['open', 'resolved', 'ignored', 'all'] as const).map((value) => (
            <button key={value} type="button" className={cn('rounded-full border px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em]', filter === value ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setFilter(value)}>
              {value === 'open' ? (zh ? '未解决' : 'Open') : value === 'resolved' ? (zh ? '已解决' : 'Resolved') : value === 'ignored' ? (zh ? '已忽略' : 'Ignored') : (zh ? '全部' : 'All')}
            </button>
          ))}
          <button type="button" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white" onClick={() => { void runConsistencyCheck({ projectRoot, scope: 'full', target_id: selectedEntity?.id ?? 'all' }).then(() => setLastActionStatus(zh ? '一致性检查完成' : 'Consistency audit complete')); }} disabled={isRunning} data-testid="run-consistency-btn">
            <RefreshCw size={14} className={cn('mr-2 inline', isRunning && 'animate-spin')} />
            {isRunning ? (zh ? '检查中' : 'Running') : zh ? '运行审计' : 'Run Audit'}
          </button>
        </div>
      </div>

      <div className="grid gap-4 border-b border-border bg-bg-elev-1 px-8 py-4 md:grid-cols-4">
        <Summary label={zh ? '未解决问题' : 'Open Issues'} value={String(issues.filter((issue) => issue.status === 'open' && issue.visibility !== 'hidden').length)} />
        <Summary label={zh ? '已解决' : 'Resolved'} value={String(issues.filter((issue) => issue.status === 'resolved').length)} />
        <Summary label={zh ? '已忽略' : 'Ignored'} value={String(issues.filter((issue) => issue.status === 'ignored').length)} />
        <Summary label={zh ? '待审修复提案' : 'Pending Fixes'} value={String(issues.filter((issue) => issue.suggestedProposalIds?.length).length)} />
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-8">
        <div className="mx-auto max-w-6xl space-y-4">
          {visibleIssues.map((issue) => (
            <div key={issue.id} className="rounded-3xl border border-border bg-card p-6 shadow-1" data-testid="consistency-issue-item">
              <div className="flex items-start justify-between gap-6">
                <div className="flex items-start gap-4">
                  <div className={cn('rounded-2xl p-3', issue.severity === 'high' ? 'bg-red/10 text-red' : issue.severity === 'medium' ? 'bg-amber/10 text-amber' : 'bg-sky-500/10 text-sky-300')}>
                    {issue.severity === 'high' ? <AlertCircle size={20} /> : <AlertTriangle size={20} />}
                  </div>
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{issue.source}</div>
                    <div className="mt-2 text-xl font-black text-text">{issue.title}</div>
                    <p className="mt-3 text-sm leading-relaxed text-text-2">{issue.description}</p>
                    {issue.fixSuggestion && <div className="mt-4 rounded-2xl border border-border bg-bg-elev-1 p-4 text-sm text-text-2"><div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-brand-2">{zh ? '修复建议' : 'Suggested Fix'}</div>{issue.fixSuggestion}</div>}
                  </div>
                </div>
                <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{issue.severity}</div>
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <button type="button" className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-white" onClick={() => queueFix(issue.id)} data-testid="consistency-queue-fix-btn"><Wrench size={14} className="mr-2 inline" />{zh ? '生成修复提案' : 'Queue Fix'}</button>
                <button type="button" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-text-2" onClick={() => resolveIssue(issue.id, 'resolved')}><CheckCircle2 size={14} className="mr-2 inline" />{zh ? '标记已解决' : 'Mark Resolved'}</button>
                <button type="button" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-text-2" onClick={() => dismissIssue(issue.id)}><EyeOff size={14} className="mr-2 inline" />{zh ? '隐藏问题' : 'Hide'}</button>
              </div>
            </div>
          ))}
          {!visibleIssues.length && (
            <div className="flex min-h-[420px] flex-col items-center justify-center rounded-3xl border border-dashed border-border bg-bg-elev-1 p-8 text-center text-text-3">
              <CheckCircle2 size={80} className="mb-5 opacity-30" />
              <div className="text-lg font-black text-text">{zh ? '当前视图没有问题' : 'No issues in this view'}</div>
              <div className="mt-2 text-sm text-text-2">{zh ? '切换筛选或重新运行审计查看最新结果。' : 'Change the filter or run an audit to refresh results.'}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const Summary = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-2xl border border-border bg-card p-4 shadow-1">
    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{label}</div>
    <div className="mt-2 text-2xl font-black text-text">{value}</div>
  </div>
);
