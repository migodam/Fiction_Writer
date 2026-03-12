import React from 'react';
import {
  Archive,
  ArrowRightLeft,
  CheckCircle2,
  History,
  Inbox,
  Layers3,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';

export const WorkbenchWorkspace = () => {
  const { sidebarSection } = useUIStore();
  const { proposals, proposalHistory, issues, resolveProposal, addGraphSyncProposal } = useProjectStore();
  const { t } = useI18n();

  return (
    <div className="flex h-full bg-bg">
      <div className="flex-1 overflow-y-auto p-8 custom-scrollbar" data-testid="agent-console">
        <WorkbenchHeader />
        {sidebarSection === 'inbox' && (
          <InboxPanel
            proposals={proposals}
            onAccept={(proposalId) => resolveProposal(proposalId, 'accepted')}
            onReject={(proposalId) => resolveProposal(proposalId, 'rejected')}
          />
        )}
        {sidebarSection === 'history' && <HistoryPanel proposalHistory={proposalHistory} />}
        {sidebarSection === 'issues' && <IssuesPanel issues={issues} />}
        {sidebarSection === 'bulk' && (
          <BulkPanel
            pendingCount={proposals.length}
            onQueueProposal={() =>
              addGraphSyncProposal(
                'Queue storyboard sync',
                'Create a proposal batch from the current graph selection and send it to Inbox.'
              )
            }
            t={t}
          />
        )}
      </div>
    </div>
  );
};

const WorkbenchHeader = () => {
  const { t } = useI18n();
  return (
  <div className="mb-8 flex items-end justify-between">
    <div>
      <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-border bg-bg-elev-1 px-3 py-1 text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
        <Sparkles size={12} />
        {t('workbench.badge')}
      </div>
      <h1 className="text-4xl font-black tracking-tight text-text">{t('workbench.title')}</h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-text-2">
        {t('workbench.body')}
      </p>
    </div>
  </div>
  );
};

const InboxPanel = ({
  proposals,
  onAccept,
  onReject,
}: {
  proposals: ReturnType<typeof useProjectStore.getState>['proposals'];
  onAccept: (proposalId: string) => void;
  onReject: (proposalId: string) => void;
}) => {
  const { t } = useI18n();
  return (
  <div className="space-y-4" data-testid="workbench-inbox-list">
    {proposals.map((proposal) => (
      <div
        key={proposal.id}
        className="rounded-2xl border border-border bg-card p-6 shadow-1"
        data-testid={`proposal-card-${proposal.id}`}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">
              {proposal.source} {t('workbench.sourceProposal')}
            </div>
            <h2 className="mt-2 text-xl font-black text-text">{proposal.title}</h2>
          </div>
          <div className="rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber">
            {t('workbench.pending')}
          </div>
        </div>
        <p className="text-sm leading-relaxed text-text-2">{proposal.description}</p>
        <div className="mt-4 rounded-xl border border-border bg-bg-elev-1 p-4 text-sm text-text-2">
          {proposal.preview}
        </div>
        <div className="mt-5 flex items-center gap-3">
          <button
            type="button"
            data-testid="proposal-accept-btn"
            className="inline-flex items-center gap-2 rounded-lg bg-green px-4 py-2 text-[11px] font-black uppercase tracking-widest text-text-invert transition-all hover:brightness-110"
            onClick={() => onAccept(proposal.id)}
          >
            <CheckCircle2 size={14} />
            {t('workbench.accept')}
          </button>
          <button
            type="button"
            data-testid="proposal-reject-btn"
            className="inline-flex items-center gap-2 rounded-lg border border-red/40 px-4 py-2 text-[11px] font-black uppercase tracking-widest text-red transition-all hover:bg-red/10"
            onClick={() => onReject(proposal.id)}
          >
            <XCircle size={14} />
            {t('workbench.reject')}
          </button>
        </div>
      </div>
    ))}
    {proposals.length === 0 && (
      <EmptyState
        icon={<Inbox size={56} />}
        title={t('workbench.inboxClear')}
        description={t('workbench.noPendingBody')}
      />
    )}
  </div>
  );
};

const HistoryPanel = ({
  proposalHistory,
}: {
  proposalHistory: ReturnType<typeof useProjectStore.getState>['proposalHistory'];
}) => {
  const { t } = useI18n();
  return (
  <div className="space-y-4" data-testid="workbench-history-list">
    {proposalHistory.map((proposal) => (
      <div key={proposal.id} className="rounded-2xl border border-border bg-card p-5 shadow-1">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">
              {proposal.source} {t('workbench.sourceResolved')}
            </div>
            <h2 className="mt-2 text-lg font-black text-text">{proposal.title}</h2>
          </div>
          <div
            className={`rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-widest ${
              proposal.status === 'accepted'
                ? 'border border-green/30 bg-green/10 text-green'
                : 'border border-red/30 bg-red/10 text-red'
            }`}
          >
            {proposal.status}
          </div>
        </div>
        <p className="mt-3 text-sm text-text-2">{proposal.preview}</p>
      </div>
    ))}
    {proposalHistory.length === 0 && (
      <EmptyState
        icon={<History size={56} />}
        title={t('workbench.noResolved')}
        description={t('workbench.noResolvedBody')}
      />
    )}
  </div>
  );
};

const IssuesPanel = ({
  issues,
}: {
  issues: ReturnType<typeof useProjectStore.getState>['issues'];
}) => {
  const { t } = useI18n();
  return (
  <div className="space-y-4" data-testid="workbench-issues-list">
    {issues.map((issue) => (
      <div key={issue.id} className="rounded-2xl border border-border bg-card p-5 shadow-1">
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-amber">
              {t('workbench.consistencyIssue')}
            </div>
            <h2 className="mt-2 text-lg font-black text-text">{issue.title}</h2>
          </div>
          <div className="rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber">
            {issue.severity}
          </div>
        </div>
        <p className="text-sm text-text-2">{issue.description}</p>
        {issue.fixSuggestion && (
          <div className="mt-4 rounded-xl border border-border bg-bg-elev-1 p-4 text-sm text-text-2">
            {issue.fixSuggestion}
          </div>
        )}
      </div>
    ))}
    {issues.length === 0 && (
      <EmptyState
        icon={<ShieldAlert size={56} />}
        title={t('workbench.noIssues')}
        description={t('workbench.noIssuesBody')}
      />
    )}
  </div>
  );
};

const BulkPanel = ({
  pendingCount,
  onQueueProposal,
  t,
}: {
  pendingCount: number;
  onQueueProposal: () => void;
  t: (key: string, fallback?: string) => string;
}) => (
  <div className="grid gap-5 md:grid-cols-2" data-testid="workbench-bulk-panel">
    <div className="rounded-2xl border border-border bg-card p-6 shadow-1">
      <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{t('workbench.queue')}</div>
      <h2 className="text-2xl font-black text-text">{pendingCount} pending proposals</h2>
      <p className="mt-3 text-sm text-text-2">{t('workbench.bulkBody')}</p>
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          data-testid="run-prompt-btn"
          className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-widest text-white"
          onClick={onQueueProposal}
        >
          <ArrowRightLeft size={14} />
          {t('workbench.queueSync')}
        </button>
        <button
          type="button"
          data-testid="retry-btn"
          className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-[11px] font-black uppercase tracking-widest text-text-2"
        >
          <RefreshCcw size={14} />
          {t('workbench.retry')}
        </button>
        <button
          type="button"
          data-testid="clear-console-btn"
          className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-[11px] font-black uppercase tracking-widest text-text-2"
        >
          <Archive size={14} />
          {t('workbench.archiveSeen')}
        </button>
      </div>
    </div>
    <div className="rounded-2xl border border-border bg-card p-6 shadow-1">
      <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Future agent dock</div>
      <h2 className="text-2xl font-black text-text">{t('workbench.bulkTitle')}</h2>
      <p className="mt-3 text-sm text-text-2">{t('workbench.futureBody')}</p>
      <button
        type="button"
        data-testid="raw-output-toggle"
        className="mt-5 inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-[11px] font-black uppercase tracking-widest text-text-2"
      >
        <Layers3 size={14} />
        {t('workbench.rawOutput')}
      </button>
    </div>
  </div>
);

const EmptyState = ({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) => (
  <div className="flex min-h-[420px] flex-col items-center justify-center rounded-3xl border border-dashed border-divider bg-bg-elev-1 p-8 text-center text-text-3">
    <div className="mb-5 opacity-30">{icon}</div>
    <h2 className="text-lg font-black uppercase tracking-[0.2em]">{title}</h2>
    <p className="mt-3 max-w-md text-sm leading-relaxed text-text-2">{description}</p>
  </div>
);
