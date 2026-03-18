import React, { useMemo, useState } from 'react';
import { Bot, CornerDownLeft, FileSearch, Layers3, SendHorizontal, Sparkles } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import type { AgentType, EntityKind, TaskRequest, TaskRun } from '../models/project';

const AGENT_OPTIONS: { id: AgentType; name: string; description: string }[] = [
  { id: 'retrieval-agent', name: 'Retrieval Agent', description: 'Gather local project context and retrieve references.' },
  { id: 'novel-writing-agent', name: 'Novel Writing Agent', description: 'Draft or revise novel scenes after explicit instruction.' },
  { id: 'script-writing-agent', name: 'Script Writing Agent', description: 'Draft screenplay/script material from scenes or outlines.' },
  { id: 'qa-consistency-agent', name: 'QA / Consistency Agent', description: 'Check consistency and prepare reviewable fixes.' },
];

const TARGETS: { type: EntityKind; label: string; ids: (state: ReturnType<typeof useProjectStore.getState>) => { id: string; label: string }[] }[] = [
  { type: 'scene', label: 'Scenes', ids: (state) => state.scenes.map((entry) => ({ id: entry.id, label: entry.title })) },
  { type: 'chapter', label: 'Chapters', ids: (state) => state.chapters.map((entry) => ({ id: entry.id, label: entry.title })) },
  { type: 'script', label: 'Scripts', ids: (state) => state.scripts.map((entry) => ({ id: entry.id, label: entry.title })) },
  { type: 'storyboard', label: 'Storyboards', ids: (state) => state.storyboards.map((entry) => ({ id: entry.id, label: entry.title })) },
];

export const AgentWorkspace = () => {
  const store = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const [agentType, setAgentType] = useState<AgentType>('retrieval-agent');
  const [targetType, setTargetType] = useState<EntityKind>('scene');
  const [targetId, setTargetId] = useState(store.scenes[0]?.id || '');
  const [instruction, setInstruction] = useState('');

  const targetOptions = useMemo(() => TARGETS.find((entry) => entry.type === targetType)?.ids(store) || [], [store, targetType]);

  const submitInstruction = () => {
    if (!instruction.trim()) return;
    const now = new Date().toISOString();
    const requestId = `task_request_${Date.now()}`;
    const runId = `task_run_${Date.now()}`;
    const taskRequest: TaskRequest = {
      id: requestId,
      title: instruction.trim().slice(0, 72),
      taskType: 'agent_instruction',
      agentType,
      source: 'manual',
      status: 'queued',
      prompt: instruction.trim(),
      input: { instruction: instruction.trim() },
      contextScope: { targetType, targetId },
      targetIds: targetId ? [{ type: targetType, id: targetId }] : [],
      reviewPolicy: agentType === 'retrieval-agent' ? 'artifact_only' : 'manual_workbench',
      createdAt: now,
    };
    const taskRun: TaskRun = {
      id: runId,
      taskRequestId: requestId,
      status: 'awaiting_user_input',
      executor: 'manual',
      adapter: 'ui-command-placeholder',
      attempt: 1,
      startedAt: now,
      heartbeatAt: now,
      summary: `Manual agent instruction queued for ${agentType}.`,
      artifactIds: [],
      awaitingUserInput: {
        prompt: 'Execution backend is not connected yet. Review the instruction and bind an executor in the next phase.',
        fields: ['executor_binding', 'review_scope'],
        reason: 'UI-level command capture is enabled, but this round does not execute agent workflows.',
      },
    };
    store.addTaskRequest(taskRequest);
    store.addTaskRun(taskRun);
    setInstruction('');
    setLastActionStatus('Agent instruction queued');
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg" data-testid="agent-workspace">
      <aside className="w-[360px] border-r border-border bg-bg-elev-1 p-6">
        <div className="mb-6 flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-brand/30 bg-brand/10 text-brand">
            <Bot size={22} />
          </div>
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Agent Console</div>
            <div className="text-sm font-black text-text">Instruction Capture Surface</div>
          </div>
        </div>

        <div className="space-y-5">
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Agent</div>
            <select value={agentType} onChange={(event) => setAgentType(event.target.value as AgentType)} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
              {AGENT_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Target Type</div>
            <select
              value={targetType}
              onChange={(event) => {
                const nextType = event.target.value as EntityKind;
                setTargetType(nextType);
                const nextOptions = TARGETS.find((entry) => entry.type === nextType)?.ids(store) || [];
                setTargetId(nextOptions[0]?.id || '');
              }}
              className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
            >
              {TARGETS.map((option) => (
                <option key={option.type} value={option.type}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Target</div>
            <select value={targetId} onChange={(event) => setTargetId(event.target.value)} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
              {targetOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Instruction</div>
            <textarea
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              className="h-48 w-full rounded-3xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2 outline-none"
              placeholder="Describe what you want the agent to do. This records a formal task request and placeholder run, but does not execute a backend workflow yet."
              data-testid="agent-command-input"
            />
          </label>

          <button
            type="button"
            className="w-full rounded-2xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.25em] text-white"
            onClick={submitInstruction}
            data-testid="agent-command-submit"
          >
            <SendHorizontal size={14} className="mr-2 inline" />
            Queue Instruction
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        <div className="mb-8 grid gap-4 md:grid-cols-3">
          <MetricCard label="Queued Requests" value={String(store.taskRequests.length)} icon={<Layers3 size={14} />} />
          <MetricCard label="Runs" value={String(store.taskRuns.length)} icon={<CornerDownLeft size={14} />} />
          <MetricCard label="Reviewable Proposals" value={String(store.proposals.length)} icon={<FileSearch size={14} />} />
        </div>

        <div className="mb-8 rounded-3xl border border-border bg-card p-6 shadow-1">
          <div className="mb-4 flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
            <Sparkles size={14} />
            Current Agent Surface Scope
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {AGENT_OPTIONS.map((option) => (
              <div key={option.id} className="rounded-2xl border border-border bg-bg-elev-1 p-4">
                <div className="text-sm font-black text-text">{option.name}</div>
                <div className="mt-2 text-sm leading-relaxed text-text-2">{option.description}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-2">
          <section className="rounded-3xl border border-border bg-card p-6 shadow-1">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Recent Requests</div>
            <div className="space-y-3">
              {store.taskRequests.slice(0, 8).map((task) => (
                <div key={task.id} className="rounded-2xl border border-border bg-bg p-4" data-testid={`agent-request-${task.id}`}>
                  <div className="text-sm font-black text-text">{task.title}</div>
                  <div className="mt-2 text-[10px] uppercase tracking-[0.2em] text-text-3">{task.agentType} / {task.status}</div>
                  <div className="mt-3 text-sm leading-relaxed text-text-2">{task.prompt}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-3xl border border-border bg-card p-6 shadow-1">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Recent Runs</div>
            <div className="space-y-3">
              {store.taskRuns.slice(0, 8).map((run) => (
                <div key={run.id} className="rounded-2xl border border-border bg-bg p-4">
                  <div className="text-sm font-black text-text">{run.summary}</div>
                  <div className="mt-2 text-[10px] uppercase tracking-[0.2em] text-text-3">{run.status} / {run.adapter}</div>
                  {run.awaitingUserInput && <div className="mt-3 text-sm leading-relaxed text-text-2">{run.awaitingUserInput.reason}</div>}
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};

const MetricCard = ({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) => (
  <div className="rounded-2xl border border-border bg-card p-4 shadow-1">
    <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-[0.2em] text-text-3">
      <span>{label}</span>
      {icon}
    </div>
    <div className="mt-2 text-2xl font-black text-text">{value}</div>
  </div>
);
