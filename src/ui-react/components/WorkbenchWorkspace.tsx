import React, { useRef, useMemo, useState } from 'react';
import { CheckCircle2, FileUp, Inbox, RefreshCw, ShieldAlert, Sparkles, UploadCloud, XCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import type { Chapter, ImportJob, Proposal, Scene, TodoItem, TodoPriority, TodoStatus } from '../models/project';

export const WorkbenchWorkspace = () => {
  const { sidebarSection, setLastActionStatus } = useUIStore();
  const {
    proposals,
    proposalHistory,
    issues,
    importJobs,
    taskRuns,
    taskArtifacts,
    promptTemplates,
    todos,
    resolveProposal,
    addImportJob,
    updateImportJob,
    addChapter,
    updateChapter,
    addScene,
    addProposal,
    createTodo,
    updateTodo,
    deleteTodo,
    setSelectedEntity,
  } = useProjectStore();
  const { locale } = useI18n();
  const zh = locale === 'zh-CN';
  const [importState, setImportState] = useState<{
    open: boolean;
    fileName: string;
    sourceFormat: 'txt' | 'md' | 'docx';
    text: string;
    previewChapters: { title: string; scenes: { title: string; content: string }[] }[];
    error: string | null;
  }>({ open: false, fileName: '', sourceFormat: 'md', text: '', previewChapters: [], error: null });
  const fileRef = useRef<HTMLInputElement | null>(null);

  const openIssues = issues.filter((issue) => issue.status === 'open' && issue.visibility !== 'hidden');

  const summary = {
    proposals: proposals.length,
    issues: openIssues.length,
    imports: importJobs.length,
    runs: taskRuns.filter((run) => ['queued', 'running', 'awaiting_user_input'].includes(run.status)).length,
    prompts: promptTemplates.length,
  };

  const confirmImport = () => {
    if (!importState.previewChapters.length) return;
    const importId = `import_${Date.now()}`;
    const canonicalChapterIds: string[] = [];
    const canonicalSceneIds: string[] = [];
    const newProposals: Proposal[] = [];

    importState.previewChapters.forEach((chapterDraft, chapterIndex) => {
      const chapterId = `chap_${Date.now()}_${chapterIndex}`;
      canonicalChapterIds.push(chapterId);
      const sceneIds: string[] = [];
      const chapter: Chapter = {
        id: chapterId,
        title: chapterDraft.title,
        summary: chapterDraft.scenes[0]?.content.slice(0, 120) || '',
        goal: '',
        notes: '',
        sceneIds,
        orderIndex: chapterIndex,
        status: 'draft',
      };
      addChapter(chapter);

      chapterDraft.scenes.forEach((sceneDraft, sceneIndex) => {
        const sceneId = `scene_${Date.now()}_${chapterIndex}_${sceneIndex}`;
        sceneIds.push(sceneId);
        canonicalSceneIds.push(sceneId);
        const scene: Scene = {
          id: sceneId,
          chapterId,
          title: sceneDraft.title,
          summary: sceneDraft.content.slice(0, 120),
          content: sceneDraft.content,
          orderIndex: sceneIndex,
          povCharacterId: null,
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedWorldItemIds: [],
          status: 'draft',
        };
        addScene(scene);
        newProposals.push({
          id: `proposal_import_${sceneId}`,
          title: `${zh ? '导入元数据待审' : 'Import metadata review'}: ${sceneDraft.title}`,
          source: 'import',
          kind: 'import_review',
          description: zh ? '请审阅角色、地点和世界设定抽取建议。' : 'Review extracted characters, locations, and world details.',
          targetEntityType: 'scene',
          targetEntityId: sceneId,
          preview: sceneDraft.content.slice(0, 240),
          reviewPolicy: 'manual_workbench',
          status: 'pending',
          createdAt: new Date().toISOString(),
        });
      });

      updateChapter({ ...chapter, sceneIds });
    });

    newProposals.forEach((proposal) => addProposal(proposal));
    const job: ImportJob = {
      id: importId,
      sourceFileName: importState.fileName,
      sourcePath: null,
      sourceFormat: importState.sourceFormat,
      status: 'completed',
      stage: 'proposal_generated',
      segmentationConfidence: importState.previewChapters.length > 1 ? 'high' : 'medium',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      taskRequestId: null,
      taskRunId: null,
      canonicalChapterIds,
      canonicalSceneIds,
      chapterCandidates: importState.previewChapters.map((chapter, index) => ({ id: `import_chapter_${index}`, title: chapter.title, summary: chapter.scenes[0]?.content.slice(0, 120) || '', confidence: 'high' })),
      sceneCandidates: importState.previewChapters.flatMap((chapter, chapterIndex) => chapter.scenes.map((scene, sceneIndex) => ({ id: `import_scene_${chapterIndex}_${sceneIndex}`, title: scene.title, summary: scene.content.slice(0, 120), confidence: 'medium' }))),
      proposalIds: newProposals.map((proposal) => proposal.id),
      issueIds: [],
      notes: [
        zh ? '章节和场景骨架已写入 canonical。' : 'Deterministic chapter/scene skeleton written to canonical project data.',
        zh ? '推断性元数据已送入 Workbench 审核。' : 'Inferred metadata was routed to Workbench proposals.',
      ],
    };
    addImportJob(job);
    setImportState({ open: false, fileName: '', sourceFormat: 'md', text: '', previewChapters: [], error: null });
    setLastActionStatus(zh ? '导入已完成并生成待审提案' : 'Import completed with review proposals');
  };

  return (
    <div className="flex h-full bg-bg">
      <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        <div className="mb-8 flex items-end justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-border bg-bg-elev-1 px-3 py-1 text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
              <Sparkles size={12} />
              {zh ? '工作台' : 'Workbench'}
            </div>
            <h1 className="text-4xl font-black tracking-tight text-text">{zh ? '审核与运行中心' : 'Review and Runtime Center'}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-text-2">
              {zh ? '所有导入、提案、运行日志和提示模板都在这里汇总。' : 'Imports, proposals, runtime logs, and prompt templates converge here.'}
            </p>
          </div>
          <button type="button" className="rounded-2xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" onClick={() => setImportState((current) => ({ ...current, open: true }))}>
            <FileUp size={14} className="mr-2 inline" />
            {zh ? '导入小说' : 'Import Novel'}
          </button>
        </div>

        <div className="mb-8 grid gap-4 md:grid-cols-5">
          <SummaryCard label={zh ? '待审提案' : 'Inbox'} value={String(summary.proposals)} />
          <SummaryCard label={zh ? '开放问题' : 'Open Issues'} value={String(summary.issues)} />
          <SummaryCard label={zh ? '导入任务' : 'Imports'} value={String(summary.imports)} />
          <SummaryCard label={zh ? '活跃运行' : 'Active Runs'} value={String(summary.runs)} />
          <SummaryCard label={zh ? '提示模板' : 'Prompt Templates'} value={String(summary.prompts)} />
        </div>

        {sidebarSection === 'inbox' && (
          <div className="space-y-4" data-testid="workbench-inbox-list">
            {proposals.map((proposal) => (
              <div key={proposal.id} className="rounded-2xl border border-border bg-card p-6 shadow-1" data-testid={`proposal-card-${proposal.id}`}>
                <div className="mb-4 flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{proposal.source}</div>
                    <h2 className="mt-2 text-xl font-black text-text">{proposal.title}</h2>
                  </div>
                  <div className="rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber">{zh ? '待处理' : 'Pending'}</div>
                </div>
                <p className="text-sm leading-relaxed text-text-2">{proposal.description}</p>
                <div className="mt-4 rounded-xl border border-border bg-bg-elev-1 p-4 text-sm text-text-2">{proposal.preview}</div>
                <div className="mt-5 flex items-center gap-3">
                  <button type="button" data-testid="proposal-accept-btn" className="inline-flex items-center gap-2 rounded-lg bg-green px-4 py-2 text-[11px] font-black uppercase tracking-widest text-text-invert" onClick={() => resolveProposal(proposal.id, 'accepted')}>
                    <CheckCircle2 size={14} />
                    {zh ? '接受' : 'Accept'}
                  </button>
                  <button type="button" data-testid="proposal-reject-btn" className="inline-flex items-center gap-2 rounded-lg border border-red/40 px-4 py-2 text-[11px] font-black uppercase tracking-widest text-red" onClick={() => resolveProposal(proposal.id, 'rejected')}>
                    <XCircle size={14} />
                    {zh ? '拒绝' : 'Reject'}
                  </button>
                </div>
              </div>
            ))}
            {proposals.length === 0 && <EmptyState icon={<Inbox size={56} />} title={zh ? '收件箱为空' : 'Inbox Clear'} description={zh ? '当前没有待审提案。' : 'There are no pending proposals.'} />}
          </div>
        )}

        {sidebarSection === 'history' && (
          <div className="space-y-4">
            {proposalHistory.map((proposal) => (
              <div key={proposal.id} className="rounded-2xl border border-border bg-card p-5 shadow-1">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{proposal.source}</div>
                    <h2 className="mt-2 text-lg font-black text-text">{proposal.title}</h2>
                  </div>
                  <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-3">{proposal.status}</div>
                </div>
                <p className="mt-3 text-sm text-text-2">{proposal.preview}</p>
              </div>
            ))}
          </div>
        )}

        {sidebarSection === 'issues' && (
          <div className="space-y-4" data-testid="workbench-issues-list">
            {openIssues.map((issue) => (
              <button key={issue.id} type="button" className="w-full rounded-2xl border border-border bg-card p-5 text-left shadow-1" onClick={() => setSelectedEntity('issue', issue.id)}>
                <div className="mb-3 flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-amber">{issue.source}</div>
                    <h2 className="mt-2 text-lg font-black text-text">{issue.title}</h2>
                  </div>
                  <div className="rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber">{issue.severity}</div>
                </div>
                <p className="text-sm text-text-2">{issue.description}</p>
              </button>
            ))}
            {openIssues.length === 0 && <EmptyState icon={<ShieldAlert size={56} />} title={zh ? '没有开放问题' : 'No Open Issues'} description={zh ? '已修复或已忽略的问题会自动移出默认视图。' : 'Resolved or dismissed issues are removed from the default view.'} />}
          </div>
        )}

        {sidebarSection === 'imports' && <ImportsPanel importJobs={importJobs} onSelect={(id) => setSelectedEntity('import_job', id)} zh={zh} onOpenImport={() => setImportState((current) => ({ ...current, open: true }))} />}

        {sidebarSection === 'runs' && (
          <div className="space-y-4">
            {taskRuns.map((run) => (
              <div key={run.id} className="rounded-2xl border border-border bg-card p-6 shadow-1">
                <div className="mb-3 flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{run.executor} / {run.adapter}</div>
                    <h2 className="mt-2 text-lg font-black text-text">{run.summary}</h2>
                  </div>
                  <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-2">{run.status}</div>
                </div>
                {run.awaitingUserInput && <div className="mb-4 rounded-xl border border-amber/30 bg-amber/10 p-4 text-sm text-text-2">{run.awaitingUserInput.reason}</div>}
                <div className="space-y-2">
                  {taskArtifacts.filter((artifact) => run.artifactIds.includes(artifact.id)).map((artifact) => (
                    <div key={artifact.id} className="rounded-xl border border-border bg-bg-elev-1 p-3 text-sm text-text-2">
                      <div className="font-bold text-text">{artifact.summary}</div>
                      <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-text-3">{artifact.type}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {sidebarSection === 'tasks' && (
          <TasksPanel
            todos={todos}
            proposals={proposals}
            createTodo={createTodo}
            updateTodo={updateTodo}
            deleteTodo={deleteTodo}
            resolveProposal={resolveProposal}
          />
        )}

        {sidebarSection === 'prompts' && (
          <div className="space-y-4">
            {promptTemplates.map((template) => (
              <button key={template.id} type="button" className="w-full rounded-2xl border border-border bg-card p-6 text-left shadow-1" onClick={() => setSelectedEntity('prompt_template', template.id)}>
                <div className="mb-3 flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{template.agentType}</div>
                    <h2 className="mt-2 text-lg font-black text-text">{template.name}</h2>
                  </div>
                  <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-2">v{template.version}</div>
                </div>
                <p className="text-sm leading-relaxed text-text-2">{template.purpose}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {template.promptTemplateSlots.map((slot) => (
                    <span key={slot.token} className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                      {slot.token}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {importState.open && (
        <ImportModal
          state={importState}
          setState={setImportState}
          fileRef={fileRef}
          onConfirm={confirmImport}
          zh={zh}
        />
      )}
    </div>
  );
};

const TasksPanel = ({
  todos,
  proposals,
  createTodo,
  updateTodo,
  deleteTodo,
  resolveProposal,
}: {
  todos: TodoItem[];
  proposals: Proposal[];
  createTodo: (item: Omit<TodoItem, 'id' | 'createdAt' | 'updatedAt'>) => void;
  updateTodo: (id: string, patch: Partial<Pick<TodoItem, 'title' | 'description' | 'status' | 'priority' | 'relatedEntityType' | 'relatedEntityId'>>) => void;
  deleteTodo: (id: string) => void;
  resolveProposal: (proposalId: string, status: Proposal['status']) => void;
}) => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { scenes, characters, chapters, setSelectedEntity } = useProjectStore();
  const [activeTab, setActiveTab] = useState<'story-gaps' | 'my-tasks' | 'agent-proposals'>('story-gaps');
  const [refreshCount, setRefreshCount] = useState<number>(0);
  const [newTitle, setNewTitle] = useState('');
  const [newPriority, setNewPriority] = useState<TodoPriority>('medium');
  const [statusFilter, setStatusFilter] = useState<TodoStatus | 'all'>('all');

  const pendingProposals = proposals.filter((p) => p.status === 'pending');
  const filteredTodos = statusFilter === 'all' ? todos : todos.filter((todo) => todo.status === statusFilter);

  const storyGaps = useMemo(() => {
    const gaps: Array<{ entityType: string; entityId: string; entityName: string; description: string }> = [];

    // Scenes with short content/summary (< 200 chars)
    for (const scene of scenes) {
      const content = (scene.content ?? scene.summary ?? '').trim();
      if (content.length < 200) {
        gaps.push({ entityType: 'scene', entityId: scene.id, entityName: scene.title, description: t('backlog.gapSceneShort').replace('{name}', scene.title) });
      }
    }
    // Characters with empty background or arc
    for (const char of characters) {
      if (!char.background?.trim()) {
        gaps.push({ entityType: 'character', entityId: char.id, entityName: char.name, description: t('backlog.gapNoBackground').replace('{name}', char.name) });
      }
      if (!char.arc?.trim()) {
        gaps.push({ entityType: 'character', entityId: `${char.id}_arc`, entityName: char.name, description: t('backlog.gapNoArc').replace('{name}', char.name) });
      }
    }
    // Chapters with no scenes
    for (const chapter of chapters) {
      if (!chapter.sceneIds?.length) {
        gaps.push({ entityType: 'chapter', entityId: chapter.id, entityName: chapter.title, description: t('backlog.gapNoScenes').replace('{name}', chapter.title) });
      }
    }
    return gaps;
  }, [scenes, characters, chapters, refreshCount, t]);

  const handleGoFix = (entityType: string, entityId: string) => {
    // Strip _arc suffix for arc gaps
    const realId = entityId.endsWith('_arc') ? entityId.slice(0, -4) : entityId;
    if (entityType === 'scene') {
      setSelectedEntity('scene', realId);
      navigate('/writing/scenes');
    } else if (entityType === 'character') {
      setSelectedEntity('character', realId);
      navigate('/characters/overview');
    } else if (entityType === 'chapter') {
      setSelectedEntity('chapter', realId);
      navigate('/writing/chapters');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    createTodo({
      title: newTitle.trim(),
      description: '',
      type: 'manual',
      status: 'pending',
      priority: newPriority,
      relatedEntityType: null,
      relatedEntityId: null,
    });
    setNewTitle('');
    setNewPriority('medium');
  };

  const priorityBadgeClass = (priority: TodoPriority) => {
    if (priority === 'high') return 'rounded-full border border-red/30 bg-red/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-red';
    if (priority === 'medium') return 'rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-brand';
    return 'rounded-full border border-border bg-bg-elev-1 px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-text-3';
  };

  const priorityLabel = (priority: TodoPriority) => {
    if (priority === 'high') return t('todo.priority.high');
    if (priority === 'medium') return t('todo.priority.medium');
    return t('todo.priority.low');
  };

  return (
    <div className="space-y-4">
      {/* Section label */}
      <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('backlog.title')}</div>

      {/* Tab bar */}
      <div className="flex gap-2">
        <button
          type="button"
          data-testid="backlog-story-gaps-tab"
          className={`rounded-lg px-4 py-2 text-[11px] font-black uppercase tracking-widest ${activeTab === 'story-gaps' ? 'bg-brand text-white' : 'border border-border text-text-2 hover:bg-hover'}`}
          onClick={() => setActiveTab('story-gaps')}
        >
          {t('backlog.storyGaps')}
          {storyGaps.length > 0 && (
            <span className="ml-2 rounded-full bg-red/20 px-1.5 text-[10px] text-red">{storyGaps.length}</span>
          )}
        </button>
        <button
          type="button"
          data-testid="backlog-tasks-tab"
          className={`rounded-lg px-4 py-2 text-[11px] font-black uppercase tracking-widest ${activeTab === 'my-tasks' ? 'bg-brand text-white' : 'border border-border text-text-2 hover:bg-hover'}`}
          onClick={() => setActiveTab('my-tasks')}
        >
          {t('backlog.myTasks')}
        </button>
        <button
          type="button"
          data-testid="backlog-proposals-tab"
          className={`rounded-lg px-4 py-2 text-[11px] font-black uppercase tracking-widest ${activeTab === 'agent-proposals' ? 'bg-brand text-white' : 'border border-border text-text-2 hover:bg-hover'}`}
          onClick={() => setActiveTab('agent-proposals')}
        >
          {t('backlog.proposals')}
          {pendingProposals.length > 0 && (
            <span className="ml-2 rounded-full bg-amber/20 px-1.5 text-[10px] text-amber">{pendingProposals.length}</span>
          )}
        </button>
      </div>

      {activeTab === 'story-gaps' && (
        <div className="space-y-3">
          {/* Refresh button */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-2">{t('backlog.gapCount').replace('{count}', String(storyGaps.length))}</span>
            <button
              type="button"
              data-testid="backlog-refresh-btn"
              onClick={() => setRefreshCount((c) => c + 1)}
              className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-[11px] font-black uppercase tracking-widest text-text-2 hover:bg-hover"
            >
              <RefreshCw size={12} />
              {t('backlog.refreshGaps')}
            </button>
          </div>
          {storyGaps.length === 0 ? (
            <p data-testid="backlog-no-gaps" className="rounded-2xl border border-dashed border-divider bg-bg-elev-1 p-6 text-center text-sm text-text-3">
              {t('backlog.noGaps')}
            </p>
          ) : (
            storyGaps.map((gap) => (
              <div
                key={gap.entityId}
                data-testid={`backlog-gap-item-${gap.entityId}`}
                className="flex items-start justify-between gap-4 rounded-2xl border border-border bg-card px-4 py-3"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-border bg-bg-elev-1 px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-text-3">
                      {gap.entityType}
                    </span>
                    <span className="text-sm font-bold text-text">{gap.entityName}</span>
                  </div>
                  <p className="mt-1 text-sm text-text-2">{gap.description}</p>
                </div>
                <button
                  type="button"
                  data-testid={`backlog-gap-fix-btn-${gap.entityId}`}
                  onClick={() => handleGoFix(gap.entityType, gap.entityId)}
                  className="shrink-0 rounded-lg border border-brand/40 px-3 py-1.5 text-[11px] font-black uppercase tracking-widest text-brand hover:bg-brand/10"
                >
                  {t('backlog.goFix')}
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'my-tasks' && (
        <div className="space-y-4">
          {/* Create form */}
          <form onSubmit={handleSubmit} className="flex gap-2 rounded-2xl border border-border bg-card p-4">
            <input
              type="text"
              data-testid="todo-create-title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('todo.taskTitle')}
              className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder-text-3 focus:outline-none focus:ring-1 focus:ring-brand"
            />
            <select
              data-testid="todo-create-priority"
              value={newPriority}
              onChange={(e) => setNewPriority(e.target.value as TodoPriority)}
              className="rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text focus:outline-none focus:ring-1 focus:ring-brand"
            >
              <option value="low">{t('todo.priority.low')}</option>
              <option value="medium">{t('todo.priority.medium')}</option>
              <option value="high">{t('todo.priority.high')}</option>
            </select>
            <button
              type="submit"
              data-testid="todo-create-submit"
              disabled={!newTitle.trim()}
              className="rounded-lg bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-widest text-white disabled:opacity-40"
            >
              {t('todo.addTask')}
            </button>
          </form>

          {/* Filter bar */}
          <div className="flex gap-2">
            {(['all', 'pending', 'done'] as const).map((filter) => (
              <button
                key={filter}
                type="button"
                data-testid={`todo-filter-${filter}`}
                className={`rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-widest ${statusFilter === filter ? 'bg-brand text-white' : 'border border-border text-text-3 hover:bg-hover'}`}
                onClick={() => setStatusFilter(filter)}
              >
                {t(`todo.status.${filter}`)}
              </button>
            ))}
          </div>

          {/* Todo list */}
          <div className="space-y-2">
            {filteredTodos.map((todo) => (
              <div
                key={todo.id}
                data-testid={`todo-item-${todo.id}`}
                className="flex items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3"
              >
                <input
                  type="checkbox"
                  data-testid={`todo-checkbox-${todo.id}`}
                  checked={todo.status === 'done'}
                  onChange={(e) => updateTodo(todo.id, { status: e.target.checked ? 'done' : 'pending' })}
                  className="h-4 w-4 rounded accent-brand"
                />
                <span className={`flex-1 text-sm ${todo.status === 'done' ? 'line-through text-text-3' : 'text-text'}`}>
                  {todo.title}
                </span>
                <span className={priorityBadgeClass(todo.priority)}>{priorityLabel(todo.priority)}</span>
                <button
                  type="button"
                  data-testid={`todo-delete-${todo.id}`}
                  onClick={() => deleteTodo(todo.id)}
                  className="rounded px-2 py-1 text-sm text-text-3 hover:bg-hover hover:text-red"
                >
                  ×
                </button>
              </div>
            ))}
            {filteredTodos.length === 0 && (
              <EmptyState
                icon={<CheckCircle2 size={56} />}
                title={t('todo.empty')}
                description={t('todo.emptyDescription')}
              />
            )}
          </div>
        </div>
      )}

      {activeTab === 'agent-proposals' && (
        <div className="space-y-4">
          {pendingProposals.map((proposal) => (
            <div
              key={proposal.id}
              data-testid={`proposal-item-${proposal.id}`}
              className="rounded-2xl border border-border bg-card p-5 shadow-1"
            >
              <div className="mb-3 flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    {proposal.confidence !== undefined && (
                      <span className="rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-widest text-brand">
                        {t('todo.confidence')}: {Math.round((proposal.confidence <= 1 ? proposal.confidence * 100 : proposal.confidence))}%
                      </span>
                    )}
                    <span className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{proposal.source}</span>
                  </div>
                  <h2 className="mt-2 text-lg font-black text-text">{proposal.title}</h2>
                  <p className="mt-1 text-sm text-text-2">{proposal.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  data-testid={`proposal-accept-${proposal.id}`}
                  onClick={() => resolveProposal(proposal.id, 'accepted')}
                  className="inline-flex items-center gap-2 rounded-lg bg-green px-4 py-2 text-[11px] font-black uppercase tracking-widest text-text-invert"
                >
                  <CheckCircle2 size={13} />
                  {t('todo.accept')}
                </button>
                <button
                  type="button"
                  data-testid={`proposal-dismiss-${proposal.id}`}
                  onClick={() => resolveProposal(proposal.id, 'rejected')}
                  className="inline-flex items-center gap-2 rounded-lg border border-red/40 px-4 py-2 text-[11px] font-black uppercase tracking-widest text-red"
                >
                  <XCircle size={13} />
                  {t('todo.dismiss')}
                </button>
              </div>
            </div>
          ))}
          {pendingProposals.length === 0 && (
            <EmptyState
              icon={<Inbox size={56} />}
              title={t('todo.proposalsEmpty')}
              description={t('todo.proposalsEmptyDescription')}
            />
          )}
        </div>
      )}
    </div>
  );
};

const ImportsPanel = ({
  importJobs,
  onSelect,
  onOpenImport,
  zh,
}: {
  importJobs: ImportJob[];
  onSelect: (id: string) => void;
  onOpenImport: () => void;
  zh: boolean;
}) => (
  <div className="space-y-4" data-testid="workbench-imports-list">
    <button type="button" className="w-full rounded-3xl border border-dashed border-brand/40 bg-bg-elev-1 p-8 text-left" onClick={onOpenImport}>
      <div className="flex items-center gap-4">
        <UploadCloud size={36} className="text-brand" />
        <div>
          <div className="text-lg font-black text-text">{zh ? '从 txt / md 导入小说' : 'Import Novel from txt / md'}</div>
          <div className="mt-2 text-sm text-text-2">{zh ? '导入向导会先预览章节/场景切分，再将元数据抽取送入 Workbench 审核。' : 'The import wizard previews chapter/scene segmentation before routing inferred metadata to Workbench review.'}</div>
        </div>
      </div>
    </button>
    {importJobs.map((job) => (
      <button key={job.id} type="button" className="w-full rounded-2xl border border-border bg-card p-6 text-left shadow-1" onClick={() => onSelect(job.id)}>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{zh ? '导入任务' : 'Import Job'}</div>
            <h2 className="mt-2 text-xl font-black text-text">{job.sourceFileName}</h2>
          </div>
          <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-2">{job.stage}</div>
        </div>
        <p className="text-sm leading-relaxed text-text-2">
          {zh
            ? `切分置信度 ${job.segmentationConfidence}，章节 ${job.chapterCandidates.length}，场景 ${job.sceneCandidates.length}，待审提案 ${job.proposalIds.length}。`
            : `Segmentation ${job.segmentationConfidence}, chapters ${job.chapterCandidates.length}, scenes ${job.sceneCandidates.length}, proposals ${job.proposalIds.length}.`}
        </p>
      </button>
    ))}
  </div>
);

const ImportModal = ({
  state,
  setState,
  fileRef,
  onConfirm,
  zh,
}: {
  state: {
    open: boolean;
    fileName: string;
    sourceFormat: 'txt' | 'md' | 'docx';
    text: string;
    previewChapters: { title: string; scenes: { title: string; content: string }[] }[];
    error: string | null;
  };
  setState: React.Dispatch<React.SetStateAction<{
    open: boolean;
    fileName: string;
    sourceFormat: 'txt' | 'md' | 'docx';
    text: string;
    previewChapters: { title: string; scenes: { title: string; content: string }[] }[];
    error: string | null;
  }>>;
  fileRef: React.RefObject<HTMLInputElement>;
  onConfirm: () => void;
  zh: boolean;
}) => (
  <div className="fixed inset-0 z-[140] flex items-center justify-center bg-black/60 p-6">
    <div className="max-h-[90vh] w-full max-w-5xl overflow-hidden rounded-[32px] border border-border bg-bg-elev-1 shadow-2">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '导入向导' : 'Import Wizard'}</div>
          <div className="mt-1 text-lg font-black text-text">{zh ? '小说导入预览' : 'Novel Import Preview'}</div>
        </div>
        <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={() => setState((current) => ({ ...current, open: false }))}>×</button>
      </div>
      <div className="grid max-h-[calc(90vh-80px)] gap-0 overflow-hidden lg:grid-cols-[360px_1fr]">
        <div className="border-r border-border bg-bg-elev-2 p-6">
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,.markdown"
            className="hidden"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              const text = await file.text();
              const sourceFormat = file.name.endsWith('.txt') ? 'txt' : file.name.endsWith('.md') || file.name.endsWith('.markdown') ? 'md' : 'docx';
              const previewChapters = parseImportPreview(text, sourceFormat);
              setState((current) => ({ ...current, fileName: file.name, sourceFormat, text, previewChapters, error: previewChapters.length ? null : (zh ? '无法解析章节结构。' : 'Unable to parse chapter structure.') }));
            }}
          />
          <button type="button" className="w-full rounded-2xl border border-brand/40 bg-brand/10 px-4 py-4 text-left text-text" onClick={() => fileRef.current?.click()}>
            <div className="text-sm font-black">{zh ? '选择文件' : 'Choose File'}</div>
            <div className="mt-2 text-xs text-text-2">{zh ? '支持 .txt / .md' : 'Supports .txt / .md'}</div>
          </button>
          <div className="mt-4 rounded-2xl border border-border bg-bg p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '文件' : 'File'}</div>
            <div className="mt-2 text-sm text-text-2">{state.fileName || (zh ? '尚未选择文件' : 'No file selected')}</div>
          </div>
          <div className="mt-4 rounded-2xl border border-border bg-bg p-4 text-sm text-text-2">
            {zh ? '导入逻辑：确定性的章节/场景骨架直接进入 canonical，角色/地点/组织等推断信息进入 Workbench 提案。' : 'Deterministic chapter/scene skeletons write to canonical storage; inferred metadata goes to Workbench proposals.'}
          </div>
          {state.error && <div className="mt-4 rounded-2xl border border-red/30 bg-red/10 p-4 text-sm text-red">{state.error}</div>}
          <button type="button" className="mt-6 w-full rounded-2xl bg-brand px-4 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white" onClick={onConfirm} disabled={!state.previewChapters.length}>
            {zh ? '确认导入' : 'Confirm Import'}
          </button>
        </div>
        <div className="overflow-y-auto custom-scrollbar p-6">
          <div className="space-y-4">
            {state.previewChapters.map((chapter, chapterIndex) => (
              <div key={`${chapter.title}-${chapterIndex}`} className="rounded-3xl border border-border bg-card p-5">
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-brand-2">{zh ? '章节预览' : 'Chapter Preview'}</div>
                <div className="mt-2 text-xl font-black text-text">{chapter.title}</div>
                <div className="mt-4 space-y-3">
                  {chapter.scenes.map((scene, sceneIndex) => (
                    <div key={`${scene.title}-${sceneIndex}`} className="rounded-2xl border border-border bg-bg-elev-1 p-4">
                      <div className="text-sm font-black text-text">{scene.title}</div>
                      <div className="mt-2 text-sm leading-relaxed text-text-2">{scene.content.slice(0, 220)}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {!state.previewChapters.length && (
              <EmptyState icon={<UploadCloud size={56} />} title={zh ? '等待导入文件' : 'Awaiting import file'} description={zh ? '选择 txt 或 md 文件后，这里会显示章节和场景预览。' : 'Choose a txt or md file to preview chapters and scenes here.'} />
            )}
          </div>
        </div>
      </div>
    </div>
  </div>
);

const parseImportPreview = (text: string, format: 'txt' | 'md' | 'docx') => {
  if (!text.trim()) return [];
  if (format === 'md') {
    const sections = text.split(/^#\s+/m).filter(Boolean);
    if (!sections.length) {
      return [{ title: 'Chapter 1', scenes: [{ title: 'Scene 1', content: text.trim() }] }];
    }
    return sections.map((section, index) => {
      const [rawTitle, ...rest] = section.split('\n');
      const body = rest.join('\n').trim();
      const sceneSections = body.split(/^##\s+/m).filter(Boolean);
      return {
        title: rawTitle.trim() || `Chapter ${index + 1}`,
        scenes: (sceneSections.length ? sceneSections : [body]).map((sceneSection, sceneIndex) => {
          if (!sceneSections.length) {
            return { title: `Scene ${sceneIndex + 1}`, content: sceneSection.trim() };
          }
          const [sceneTitle, ...sceneBody] = sceneSection.split('\n');
          return { title: sceneTitle.trim() || `Scene ${sceneIndex + 1}`, content: sceneBody.join('\n').trim() };
        }),
      };
    });
  }

  const chapters = text.split(/(?:^|\n)(?:Chapter\s+\d+|CHAPTER\s+\d+|第.+章|序章|尾声)\s*/g).filter(Boolean);
  const labels = Array.from(text.matchAll(/(?:^|\n)(Chapter\s+\d+|CHAPTER\s+\d+|第.+章|序章|尾声)\s*/g)).map((match) => match[1]);
  const resolvedChapters = (chapters.length ? chapters : [text]).map((chapterText, index) => {
    const sceneBodies = chapterText.split(/\n{2,}/).filter((entry) => entry.trim());
    return {
      title: labels[index] || `Chapter ${index + 1}`,
      scenes: sceneBodies.map((body, sceneIndex) => ({ title: `Scene ${sceneIndex + 1}`, content: body.trim() })),
    };
  });
  return resolvedChapters.length ? resolvedChapters : [{ title: 'Chapter 1', scenes: [{ title: 'Scene 1', content: text.trim() }] }];
};

const EmptyState = ({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) => (
  <div className="flex min-h-[260px] flex-col items-center justify-center rounded-3xl border border-dashed border-divider bg-bg-elev-1 p-8 text-center text-text-3">
    <div className="mb-5 opacity-30">{icon}</div>
    <h2 className="text-lg font-black uppercase tracking-[0.2em]">{title}</h2>
    <p className="mt-3 max-w-md text-sm leading-relaxed text-text-2">{description}</p>
  </div>
);

const SummaryCard = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-2xl border border-border bg-card p-4 shadow-1">
    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{label}</div>
    <div className="mt-2 text-2xl font-black text-text">{value}</div>
  </div>
);
