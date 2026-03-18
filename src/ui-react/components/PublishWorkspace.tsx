import React, { useMemo, useState } from 'react';
import { Download, FileText, Globe2, Layers3, ScrollText } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { projectService } from '../services/projectService';
import { useI18n } from '../i18n';

export const PublishWorkspace = () => {
  const { currentProject, addExportArtifact, exports, videoPackages, storyboards, chapters } = useProjectStore();
  const { sidebarSection, setLastActionStatus, appSettings } = useUIStore();
  const { locale } = useI18n();
  const zh = locale === 'zh-CN';
  const [includeAppendices, setIncludeAppendices] = useState(true);
  const [scope, setScope] = useState<'project' | 'chapter'>(appSettings.defaultChapterExportScope || 'project');
  const [format, setFormat] = useState<'markdown' | 'html'>(appSettings.defaultExportFormat || 'markdown');
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>([]);

  const previewSource = useMemo(() => {
    if (!currentProject) return '';
    return projectService.renderExport(currentProject, {
      format,
      includeAppendices,
      scope,
      chapterIds: selectedChapterIds,
    });
  }, [currentProject, format, includeAppendices, scope, selectedChapterIds]);

  const handleExport = () => {
    if (!currentProject) return;
    const artifact = projectService.exportProject(currentProject, {
      format,
      includeAppendices,
      scope,
      chapterIds: selectedChapterIds,
    });
    addExportArtifact(artifact);
    setLastActionStatus(`${format.toUpperCase()} ${zh ? '已导出' : 'exported'}`);
  };

  if (sidebarSection === 'video') {
    return (
      <div className="flex h-full overflow-hidden bg-bg" data-testid="publish-video-workspace">
        <div className="w-96 border-r border-border bg-bg-elev-1 p-6">
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '视频工作流' : 'Video Workflow'}</div>
          <h1 className="mt-3 text-3xl font-black text-text">{currentProject?.metadata.name}</h1>
          <p className="mt-3 text-sm leading-relaxed text-text-2">
            {zh ? '当前只落任务包、payload 和 manifest，不伪装成真实视频生成。' : 'This round persists prompt packages, payloads, and manifests without pretending real video generation is wired in.'}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <div className="mb-6 grid gap-4 md:grid-cols-3">
            <ManifestCard label={zh ? '任务包' : 'Packages'} value={String(videoPackages.length)} />
            <ManifestCard label={zh ? '可用分镜' : 'Ready storyboards'} value={String(storyboards.length)} />
            <ManifestCard label={zh ? '已配置 provider' : 'Configured providers'} value={String(videoPackages.filter((entry) => entry.status !== 'not_configured' && entry.status !== 'unsupported').length)} />
          </div>
          <div className="grid gap-4">
            {videoPackages.map((videoPackage) => {
              const storyboard = storyboards.find((entry) => entry.id === videoPackage.storyboardId);
              return (
                <div key={videoPackage.id} className="rounded-2xl border border-border bg-card p-6 shadow-1" data-testid={`video-package-${videoPackage.id}`}>
                  <div className="mb-3 flex items-start justify-between gap-4">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{videoPackage.provider}</div>
                      <h2 className="mt-2 text-xl font-black text-text">{videoPackage.id}</h2>
                    </div>
                    <div className="rounded-full border border-border px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-2">{videoPackage.status}</div>
                  </div>
                  <p className="text-sm text-text-2">{zh ? '分镜' : 'Storyboard'}: {storyboard?.title || videoPackage.storyboardId}</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <ManifestCard label={zh ? 'Prompt 包' : 'Prompt package'} value={videoPackage.promptPackagePath} />
                    <ManifestCard label={zh ? 'Provider 请求' : 'Provider payload'} value={videoPackage.providerPayloadPath || 'Pending'} />
                    <ManifestCard label={zh ? 'Provider 响应' : 'Provider response'} value={videoPackage.providerResponsePath || 'Pending'} />
                    <ManifestCard label={zh ? 'Render Manifest' : 'Render manifest'} value={videoPackage.renderManifestPath || 'Pending'} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-bg" data-testid="publish-workspace">
      <div className="w-[360px] border-r border-border bg-bg-elev-1 p-6" data-testid="publish-controls">
        <div className="mb-8">
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '发布台' : 'Publishing Desk'}</div>
          <h1 className="mt-3 text-3xl font-black text-text">{currentProject?.metadata.name}</h1>
          <p className="mt-3 text-sm leading-relaxed text-text-2">{zh ? '支持整本导出，也支持按章节导出。' : 'Export the full project or a selected chapter subset.'}</p>
        </div>

        <div className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-1">
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{zh ? '导出范围' : 'Scope'}</div>
            <select value={scope} onChange={(event) => setScope(event.target.value as 'project' | 'chapter')} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
              <option value="project">{zh ? '整本项目' : 'Whole project'}</option>
              <option value="chapter">{zh ? '按章节' : 'By chapter'}</option>
            </select>
          </label>

          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{zh ? '导出格式' : 'Format'}</div>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" className={`rounded-xl border px-4 py-3 text-sm ${format === 'markdown' ? 'border-brand bg-active text-text' : 'border-border text-text-2'}`} onClick={() => setFormat('markdown')}><FileText size={16} className="mr-2 inline" />Markdown</button>
              <button type="button" className={`rounded-xl border px-4 py-3 text-sm ${format === 'html' ? 'border-brand bg-active text-text' : 'border-border text-text-2'}`} onClick={() => setFormat('html')}><Globe2 size={16} className="mr-2 inline" />HTML</button>
            </div>
          </label>

          <label className="flex items-center justify-between gap-4 text-sm text-text">
            <span className="flex items-center gap-3"><Layers3 size={16} /> {zh ? '附带附录' : 'Include appendices'}</span>
            <input type="checkbox" checked={includeAppendices} onChange={(event) => setIncludeAppendices(event.target.checked)} data-testid="publish-appendices-toggle" />
          </label>

          {scope === 'chapter' && (
            <div>
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{zh ? '选择章节' : 'Select chapters'}</div>
              <div className="max-h-64 space-y-2 overflow-y-auto rounded-2xl border border-border bg-bg p-3">
                {chapters.map((chapter) => {
                  const checked = selectedChapterIds.includes(chapter.id);
                  return (
                    <label key={chapter.id} className="flex items-center gap-3 rounded-xl border border-transparent px-2 py-2 text-sm text-text-2 hover:bg-hover">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setSelectedChapterIds((current) =>
                            checked ? current.filter((id) => id !== chapter.id) : [...current, chapter.id],
                          )
                        }
                      />
                      <span>{chapter.title}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          <button type="button" className="flex w-full items-center justify-between rounded-xl border border-border px-4 py-3 text-left text-text transition-colors hover:border-brand" onClick={handleExport} data-testid="publish-export-action">
            <span className="flex items-center gap-3"><Download size={18} /> {zh ? '生成导出' : 'Generate export'}</span>
            <span className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{format}</span>
          </button>
        </div>

        <div className="mt-8 rounded-2xl border border-border bg-card p-5 shadow-1" data-testid="publish-export-history">
          <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{zh ? '导出历史' : 'Generated Exports'}</div>
          <div className="space-y-3">
            {exports.length > 0 ? exports.map((artifact) => (
              <div key={artifact.id} className="rounded-xl border border-border bg-bg p-3">
                <div className="text-sm font-bold text-text">{artifact.fileName}</div>
                <div className="mt-1 text-[11px] text-text-3">{artifact.path || 'In-memory preview'}</div>
                <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">{artifact.scope} {artifact.chapterIds?.length ? `/${artifact.chapterIds.length} chapters` : ''}</div>
              </div>
            )) : <div className="text-sm text-text-3">{zh ? '暂无导出记录。' : 'No exports yet.'}</div>}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8" data-testid="publish-preview-panel">
        <div className="mb-4 flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">
          <ScrollText size={14} /> {zh ? '导出预览' : 'Preview'}
        </div>
        <pre className="whitespace-pre-wrap rounded-2xl border border-border bg-card p-6 text-sm leading-relaxed text-text-2 shadow-1">{previewSource}</pre>
      </div>
    </div>
  );
};

const ManifestCard = ({ label, value }: { label: string; value: string | null }) => (
  <div className="rounded-xl border border-border bg-bg-elev-1 p-4">
    <div className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{label}</div>
    <div className="mt-2 break-all text-sm text-text-2">{value || 'Pending'}</div>
  </div>
);
