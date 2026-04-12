import React, { useEffect, useRef, useState } from 'react';
import { Bot, Send, User, Clock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useProjectStore, useUIStore } from '../../store';
import { useI18n } from '../../i18n';
import { electronApi } from '../../services/electronApi';
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
  const { updateTaskRun } = store;
  const { setLastActionStatus, agentChatMode, agentChatMessages, setAgentChatMode, addAgentChatMessage } = useUIStore();
  const { t } = useI18n();

  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [agentChatMessages]);

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg: ChatMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    addAgentChatMessage(userMsg);
    setInput('');
    setIsLoading(true);

    // Create task request for workbench tracking
    const createdAt = new Date().toISOString();
    const requestId = `task_request_${Date.now()}`;
    const runId = `task_run_${Date.now()}`;
    const agentType = MODE_AGENT_MAP[agentChatMode];

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
      status: 'running',
      executor: 'langgraph',
      adapter: 'ai:chat',
      attempt: 1,
      startedAt: createdAt,
      heartbeatAt: createdAt,
      summary: t('agent.chat.processing'),
      artifactIds: [],
    });

    try {
      // Build conversation history for AI context
      const history = agentChatMessages.slice(-10).map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }));
      history.push({ role: 'user', content: trimmed });

      const aiResponse = await electronApi.aiChat(history);

      updateTaskRun(runId, {
        status: 'completed',
        summary: aiResponse.slice(0, 120),
        finishedAt: new Date().toISOString(),
      });

      const assistantMsg: ChatMessage = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: aiResponse,
        taskRunId: runId,
        timestamp: new Date().toISOString(),
      };
      addAgentChatMessage(assistantMsg);
      setLastActionStatus(t('agent.chat.responseReceived'));
    } catch (err) {
      updateTaskRun(runId, {
        status: 'failed',
        summary: String(err).slice(0, 120),
        finishedAt: new Date().toISOString(),
      });
      const errorContent = t('agent.chat.errorMessage').replace('{error}', String(err));
      addAgentChatMessage({
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: errorContent,
        taskRunId: runId,
        timestamp: new Date().toISOString(),
      });
      setLastActionStatus(t('agent.chat.sendFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  const modes: { id: ChatMode; i18nKey: string }[] = [
    { id: 'writing', i18nKey: 'agent.chat.mode.writing' },
    { id: 'consistency', i18nKey: 'agent.chat.mode.consistency' },
    { id: 'simulation', i18nKey: 'agent.chat.mode.simulation' },
    { id: 'retrieval', i18nKey: 'agent.chat.mode.retrieval' },
    { id: 'general', i18nKey: 'agent.chat.mode.general' },
  ];

  return (
    <div className="flex h-full flex-col bg-bg" data-testid="agent-chat">
      {/* Mode tabs */}
      <div className="flex items-center gap-1 border-b border-border bg-bg-elev-1 px-4 py-2 overflow-x-auto">
        {modes.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setAgentChatMode(m.id)}
            className={cn(
              'shrink-0 rounded-xl px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] transition-colors',
              agentChatMode === m.id ? 'bg-brand text-white' : 'text-text-2 hover:bg-hover',
            )}
          >
            {t(m.i18nKey)}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-6 space-y-4">
        {agentChatMessages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} taskRuns={store.taskRuns} />
        ))}
        {isLoading && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-border bg-bg-elev-1 text-text-2">
              <Bot size={14} />
            </div>
            <div className="rounded-2xl border border-border bg-card px-4 py-3">
              <Loader2 size={14} className="animate-spin text-brand" />
            </div>
          </div>
        )}
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
                void sendMessage();
              }
            }}
            className="flex-1 resize-none bg-transparent text-sm text-text outline-none placeholder:text-text-3"
            placeholder={t('agent.chat.placeholderExtended')}
            rows={2}
            data-testid="agent-chat-input"
          />
          <button
            type="button"
            onClick={() => void sendMessage()}
            disabled={!input.trim() || isLoading}
            title={t('agent.chat.send')}
            className="rounded-xl bg-brand p-2.5 text-white disabled:opacity-40"
            data-testid="agent-chat-send"
          >
            <Send size={15} />
          </button>
        </div>
        <div className="mt-2 text-[10px] text-text-3">
          {t('agent.chat.modeInfo').replace('{mode}', t(modes.find((m) => m.id === agentChatMode)?.i18nKey || '')).replace('{agent}', MODE_AGENT_MAP[agentChatMode])}
        </div>
      </div>
    </div>
  );
};

const ChatBubble: React.FC<{ message: ChatMessage; taskRuns: ReturnType<typeof useProjectStore.getState>['taskRuns'] }> = ({ message, taskRuns }) => {
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
          <TaskRunCard run={taskRun} />
        )}
        <div className="text-[10px] text-text-3">
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
};

const TaskRunCard: React.FC<{ run: ReturnType<typeof useProjectStore.getState>['taskRuns'][number] }> = ({ run }) => {
  const { t } = useI18n();
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
        <span>{t('agent.chat.taskStatus').replace('{status}', run.status)}</span>
      </div>
      <div className="mt-1 text-sm text-text-2">{run.summary}</div>
    </div>
  );
};
