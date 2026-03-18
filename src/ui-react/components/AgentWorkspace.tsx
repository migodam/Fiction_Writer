import React, { useMemo, useState } from 'react';
import { Bot, CornerDownLeft, FileSearch, Layers3, SendHorizontal, Sparkles } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import type { AgentType, EntityKind, TaskRequest, TaskRun } from '../models/project';
import { useI18n } from '../i18n';

const AGENT_OPTIONS: { id: AgentType; name: { en: string; zh: string }; description: { en: string; zh: string } }[] = [
  { id: 'retrieval-agent', name: { en: 'Retrieval Agent', zh: '检索 Agent' }, description: { en: 'Gather project context and references.', zh: '检索项目上下文和参考内容。' } },
  { id: 'novel-writing-agent', name: { en: 'Novel Writing Agent', zh: '小说写作 Agent' }, description: { en: 'Draft or revise novel material.', zh: '辅助起草或改写小说内容。' } },
  { id: 'script-writing-agent', name: { en: 'Script Writing Agent', zh: '剧本写作 Agent' }, description: { en: 'Draft screenplay/script content.', zh: '辅助起草剧本与分场内容。' } },
  { id: 'qa-consistency-agent', name: { en: 'QA / Consistency Agent', zh: 'QA / 一致性 Agent' }, description: { en: 'Check consistency and prepare fixes.', zh: '检查一致性并准备修复建议。' } },
];

const TARGETS: { type: EntityKind; labels: { en: string; zh: string }; ids: (state: ReturnType<typeof useProjectStore.getState>) => { id: string; label: string }[] }[] = [
  { type: 'scene', labels: { en: 'Scenes', zh: '场景' }, ids: (state) => state.scenes.map((entry) => ({ id: entry.id, label: entry.title })) },
  { type: 'chapter', labels: { en: 'Chapters', zh: '章节' }, ids: (state) => state.chapters.map((entry) => ({ id: entry.id, label: entry.title })) },
  { type: 'script', labels: { en: 'Scripts', zh: '剧本' }, ids: (state) => state.scripts.map((entry) => ({ id: entry.id, label: entry.title })) },
  { type: 'storyboard', labels: { en: 'Storyboards', zh: '分镜' }, ids: (state) => state.storyboards.map((entry) => ({ id: entry.id, label: entry.title })) },
];

export const AgentWorkspace = () => {
  const store = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { locale } = useI18n();
  const zh = locale === 'zh-CN';
  const [agentType, setAgentType] = useState<AgentType>('retrieval-agent');
  const [targetType, setTargetType] = useState<EntityKind>('scene');
  const [targetId, setTargetId] = useState(store.scenes[0]?.id || '');
  const [instruction, setInstruction] = useState('');

  const targetOptions = useMemo(() => TARGETS.find((entry) => entry.type === targetType)?.ids(store) || [], [store, targetType]);

  const submitInstruction = () => {
    if (!instruction.trim()) return;
    const createdAt = new Date().toISOString();
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
      createdAt,
    };
    const taskRun: TaskRun = {
      id: runId,
      taskRequestId: requestId,
      status: 'awaiting_user_input',
      executor: 'manual',
      adapter: 'ui-command-placeholder',
      attempt: 1,
      startedAt: createdAt,
      heartbeatAt: createdAt,
      summary: zh ? `已记录 ${AGENT_OPTIONS.find((option) => option.id === agentType)?.name.zh} 指令。` : `Queued instruction for ${agentType}.`,
      artifactIds: [],
      awaitingUserInput: {
        prompt: zh ? '当前只记录正式任务请求，真实执行器将在下一轮接入。' : 'This surface records formal task requests only. Real executors arrive in the next phase.',
        fields: ['executor_binding', 'review_scope'],
        reason: zh ? '本轮只实现控制台与任务捕获界面。' : 'This round only implements the console and task capture surface.',
      },
    };
    store.addTaskRequest(taskRequest);
    store.addTaskRun(taskRun);
    setInstruction('');
    setLastActionStatus(zh ? 'Agent 指令已排队' : 'Agent instruction queued');
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg" data-testid="agent-workspace">
      <aside className="w-[380px] border-r border-border bg-bg-elev-1 p-6">
        <div className="mb-6 flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-brand/30 bg-brand/10 text-brand">
            <Bot size={22} />
          </div>
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? 'Agent 控制台' : 'Agent Console'}</div>
            <div className="text-sm font-black text-text">{zh ? '任务指令入口' : 'Instruction Capture'}</div>
          </div>
        </div>

        <div className="space-y-5">
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{zh ? 'Agent 类型' : 'Agent'}</div>
            <select value={agentType} onChange={(event) => setAgentType(event.target.value as AgentType)} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
              {AGENT_OPTIONS.map((option) => <option key={option.id} value={option.id}>{zh ? option.name.zh : option.name.en}</option>)}
            </select>
          </label>
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{zh ? '目标类型' : 'Target Type'}</div>
            <select value={targetType} onChange={(event) => {
              const nextType = event.target.value as EntityKind;
              setTargetType(nextType);
              const nextOptions = TARGETS.find((entry) => entry.type === nextType)?.ids(store) || [];
              setTargetId(nextOptions[0]?.id || '');
            }} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
              {TARGETS.map((option) => <option key={option.type} value={option.type}>{zh ? option.labels.zh : option.labels.en}</option>)}
            </select>
          </label>
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{zh ? '目标对象' : 'Target'}</div>
            <select value={targetId} onChange={(event) => setTargetId(event.target.value)} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
              {targetOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
            </select>
          </label>
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{zh ? '指令内容' : 'Instruction'}</div>
            <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} className="h-48 w-full rounded-3xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2 outline-none" placeholder={zh ? '描述你希望 Agent 做什么。本轮会记录任务与占位 run，不会真的调用后端执行。' : 'Describe what the agent should do. This round records formal tasks and placeholder runs only.'} data-testid="agent-command-input" />
          </label>
          <button type="button" className="w-full rounded-2xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.25em] text-white" onClick={submitInstruction} data-testid="agent-command-submit">
            <SendHorizontal size={14} className="mr-2 inline" />
            {zh ? '发送指令' : 'Queue Instruction'}
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        <div className="mb-8 grid gap-4 md:grid-cols-3">
          <MetricCard label={zh ? '任务请求' : 'Queued Requests'} value={String(store.taskRequests.length)} icon={<Layers3 size={14} />} />
          <MetricCard label={zh ? '运行记录' : 'Runs'} value={String(store.taskRuns.length)} icon={<CornerDownLeft size={14} />} />
          <MetricCard label={zh ? '待审提案' : 'Reviewable Proposals'} value={String(store.proposals.length)} icon={<FileSearch size={14} />} />
        </div>

        <div className="mb-8 rounded-3xl border border-border bg-card p-6 shadow-1">
          <div className="mb-4 flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
            <Sparkles size={14} />
            {zh ? '当前控制台范围' : 'Current Console Scope'}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {AGENT_OPTIONS.map((option) => (
              <div key={option.id} className="rounded-2xl border border-border bg-bg-elev-1 p-4">
                <div className="text-sm font-black text-text">{zh ? option.name.zh : option.name.en}</div>
                <div className="mt-2 text-sm leading-relaxed text-text-2">{zh ? option.description.zh : option.description.en}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-2">
          <section className="rounded-3xl border border-border bg-card p-6 shadow-1">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{zh ? '最近任务请求' : 'Recent Requests'}</div>
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
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{zh ? '最近运行记录' : 'Recent Runs'}</div>
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
