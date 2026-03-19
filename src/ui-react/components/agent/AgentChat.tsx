import React, { useEffect, useRef, useState } from 'react';
import { Bot, Send, User, Clock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useProjectStore, useUIStore } from '../../store';
import { useI18n } from '../../i18n';
import type { AgentType, EntityKind } from '../../models/project';
import { cn } from '../../utils';

type ChatMode = 'writing' | 'consistency' | 'simulation' | 'retrieval' | 'general';

const MODE_AGENT_MAP: Record<ChatMode, AgentType> = {
  writing: 'novel-writing-agent',
  consistency: 'qa-consistency-agent',
  simulation: 'qa-consistency-agent',
  retrieval: 'retrieval-agent',
  general: 'novel-writing-agent',
};

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  taskRunId?: string;
  timestamp: string;
}

export const AgentChat: React.FC = () => {
  const store = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { locale } = useI18n();
  const zh = locale === 'zh-CN';

  const [mode, setMode] = useState<ChatMode>('general');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: zh
        ? '你好！我是叙事助理。你可以告诉我你想做什么——写作、一致性检查、推演，或者检索项目信息。'
        : "Hello! I'm your Narrative Assistant. Tell me what you'd like to do — write, check consistency, simulate, or retrieve project information.",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    const userMsg: ChatMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');

    // Create task request + run
    const createdAt = new Date().toISOString();
    const requestId = `task_request_${Date.now()}`;
    const runId = `task_run_${Date.now()}`;
    const agentType = MODE_AGENT_MAP[mode];

    store.addTaskRequest({
      id: requestId,
      title: trimmed.slice(0, 72),
      taskType: 'agent_instruction',
      agentType,
      source: 'manual',
      status: 'queued',
      prompt: trimmed,
      input: { instruction: trimmed },
      contextScope: { targetType: 'scene' as EntityKind, targetId: store.scenes[0]?.id || '' },
      targetIds: [],
      reviewPolicy: agentType === 'retrieval-agent' ? 'artifact_only' : 'manual_workbench',
      createdAt,
    });

    store.addTaskRun({
      id: runId,
      taskRequestId: requestId,
      status: 'awaiting_user_input',
      executor: 'manual',
      adapter: 'ui-chat-placeholder',
      attempt: 1,
      startedAt: createdAt,
      heartbeatAt: createdAt,
      summary: zh ? `已记录指令，等待执行器接入。` : 'Instruction queued. Awaiting executor connection.',
      artifactIds: [],
      awaitingUserInput: {
        prompt: zh ? '真实 AI 执行器将在 Phase 2 接入。' : 'Real AI executors will connect in Phase 2.',
        fields: [],
        reason: zh ? '当前为 Phase 1：记录任务，展示 UI 交互流程。' : 'Phase 1: recording tasks and demonstrating UI flow.',
      },
    });

    // Assistant reply card
    setTimeout(() => {
      const assistantMsg: ChatMessage = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: zh
          ? `已收到你的请求并创建任务。任务 ID：${requestId.slice(-8)}。\n\n当前为 Phase 1，真实 AI 执行器尚未接入，但任务已记录到 Workbench → Runs 中供后续处理。`
          : `Your request has been recorded as a task (ID: ${requestId.slice(-8)}).\n\nThis is Phase 1 — real AI executors aren't connected yet, but the task is logged in Workbench → Runs for processing.`,
        taskRunId: runId,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setLastActionStatus(zh ? '任务已记录' : 'Task recorded');
    }, 400);
  };

  const modes: { id: ChatMode; label: string; labelZh: string }[] = [
    { id: 'writing', label: 'Writing', labelZh: '写作' },
    { id: 'consistency', label: 'Consistency', labelZh: '一致性' },
    { id: 'simulation', label: 'Simulation', labelZh: '推演' },
    { id: 'retrieval', label: 'Retrieval', labelZh: '检索' },
    { id: 'general', label: 'General', labelZh: '通用' },
  ];

  return (
    <div className="flex h-full flex-col bg-bg" data-testid="agent-chat">
      {/* Mode tabs */}
      <div className="flex items-center gap-1 border-b border-border bg-bg-elev-1 px-4 py-2 overflow-x-auto">
        {modes.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={cn(
              'shrink-0 rounded-xl px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] transition-colors',
              mode === m.id ? 'bg-brand text-white' : 'text-text-2 hover:bg-hover',
            )}
          >
            {zh ? m.labelZh : m.label}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-6 space-y-4">
        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} zh={zh} taskRuns={store.taskRuns} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-border bg-bg-elev-1 px-4 py-3">
        <div className="flex items-end gap-3 rounded-2xl border border-border bg-bg px-4 py-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            className="flex-1 resize-none bg-transparent text-sm text-text outline-none placeholder:text-text-3"
            placeholder={zh ? '告诉我你想做什么... (Enter 发送, Shift+Enter 换行)' : 'Tell me what you want to do... (Enter to send, Shift+Enter for newline)'}
            rows={2}
            data-testid="agent-chat-input"
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={!input.trim()}
            title={zh ? '发送' : 'Send'}
            className="rounded-xl bg-brand p-2.5 text-white disabled:opacity-40"
            data-testid="agent-chat-send"
          >
            <Send size={15} />
          </button>
        </div>
        <div className="mt-2 text-[10px] text-text-3">
          {zh ? `模式：${modes.find((m) => m.id === mode)?.labelZh} · Agent：${MODE_AGENT_MAP[mode]}` : `Mode: ${mode} · Agent: ${MODE_AGENT_MAP[mode]}`}
        </div>
      </div>
    </div>
  );
};

const ChatBubble: React.FC<{ message: ChatMessage; zh: boolean; taskRuns: ReturnType<typeof useProjectStore.getState>['taskRuns'] }> = ({ message, zh, taskRuns }) => {
  const isUser = message.role === 'user';
  const taskRun = message.taskRunId ? taskRuns.find((r) => r.id === message.taskRunId) : null;

  return (
    <div className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}>
      <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-xl', isUser ? 'bg-brand/10 text-brand' : 'border border-border bg-bg-elev-1 text-text-2')}>
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>
      <div className={cn('max-w-[75%] space-y-2', isUser ? 'items-end' : 'items-start')}>
        <div className={cn('rounded-2xl px-4 py-3 text-sm leading-relaxed', isUser ? 'bg-brand text-white rounded-tr-sm' : 'border border-border bg-card text-text-2 rounded-tl-sm')}>
          {message.content.split('\n').map((line, i) => (
            <React.Fragment key={i}>{line}{i < message.content.split('\n').length - 1 && <br />}</React.Fragment>
          ))}
        </div>
        {taskRun && (
          <TaskRunCard run={taskRun} zh={zh} />
        )}
        <div className="text-[10px] text-text-3">
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
};

const TaskRunCard: React.FC<{ run: ReturnType<typeof useProjectStore.getState>['taskRuns'][number]; zh: boolean }> = ({ run }) => {
  const statusIconMap: Record<string, React.ReactNode> = {
    queued: <Clock size={12} className="text-amber-400" />,
    running: <Loader2 size={12} className="text-brand animate-spin" />,
    awaiting_user_input: <AlertCircle size={12} className="text-amber-400" />,
    completed: <CheckCircle size={12} className="text-green-400" />,
    failed: <AlertCircle size={12} className="text-red-400" />,
    canceled: <AlertCircle size={12} className="text-text-3" />,
  };
  const statusIcon = statusIconMap[run.status] ?? <Clock size={12} />;

  return (
    <div className="rounded-2xl border border-border bg-bg-elev-1 px-4 py-3">
      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
        {statusIcon}
        <span>Task · {run.status}</span>
      </div>
      <div className="mt-1 text-sm text-text-2">{run.summary}</div>
    </div>
  );
};
