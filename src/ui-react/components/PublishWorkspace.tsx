import React, { useMemo, useState } from 'react';
import { Download, FileText, Globe2, Layers3, ScrollText } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { projectService } from '../services/projectService';
import { useI18n } from '../i18n';

export const PublishWorkspace = () => {
  const { currentProject, addExportArtifact, exports, videoPackages, storyboards, chapters } = useProjectStore();
  const { sidebarSection, setLastActionStatus, appSettings } = useUIStore();
  const { t } = useI18n();
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
    setLastActionStatus(`${format.toUpperCase()} ${t('publish.exported', 'exported')}`);
  };

  if (sidebarSection === 'video') {
    return (
      <div className="flex h-full overflow-hidden bg-bg" data-testid="publish-video-workspace">
        <div className="w-96 border-r border-border bg-bg-elev-1 p-6">
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('publish.videoWorkflow', 'Video Workflow')}</div>
          <h1 className="mt-3 text-3xl font-black text-text">{currentProject?.metadata.name}</h1>
          <p className="mt-3 text-sm leading-relaxed text-text-2">
            {t('publish.videoWorkflowDesc', 'This round persists prompt packages, payloads, and manifests without pretending real video generation is wired in.')}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <div className="mb-6 grid gap-4 md:grid-cols-3">
            <ManifestCard label={t('publish.packages', 'Packages')} value={String(videoPackages.length)} />
            <ManifestCard label={t('publish.readyStoryboards', 'Ready storyboards')} value={String(storyboards.length)} />
            <ManifestCard label={t('publish.configuredProviders', 'Configured providers')} value={String(videoPackages.filter((entry) => entry.status !== 'not_configured' && entry.status !== 'unsupported').length)} />
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
                  <p className="text-sm text-text-2">{t('publish.storyboard', 'Storyboard')}: {storyboard?.title || videoPackage.storyboardId}</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <ManifestCard label={t('publish.promptPackage', 'Prompt package')} value={videoPackage.promptPackagePath} />
                    <ManifestCard label={t('publish.providerPayload', 'Provider payload')} value={videoPackage.providerPayloadPath || 'Pending'} />
                    <ManifestCard label={t('publish.providerResponse', 'Provider response')} value={videoPackage.providerResponsePath || 'Pending'} />
                    <ManifestCard label={t('publish.renderManifest', 'Render manifest')} value={videoPackage.renderManifestPath || 'Pending'} />
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
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('publish.publishingDesk', 'Publishing Desk')}</div>
          <h1 className="mt-3 text-3xl font-black text-text">{currentProject?.metadata.name}</h1>
          <p className="mt-3 text-sm leading-relaxed text-text-2">{t('publish.exportFullProject', 'Export the full project or a selected chapter subset.')}</p>
        </div>

        <div className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-1">
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('publish.scope', 'Scope')}</div>
            <select value={scope} onChange={(event) => setScope(event.target.value as 'project' | 'chapter')} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none">
              <option value="project">{t('publish.wholeProject', 'Whole project')}</option>
              <option value="chapter">{t('publish.byChapter', 'By chapter')}</option>
            </select>
          </label>

          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('publish.format', 'Format')}</div>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" className={`rounded-xl border px-4 py-3 text-sm ${format === 'markdown' ? 'border-brand bg-active text-text' : 'border-border text-text-2'}`} onClick={() => setFormat('markdown')}><FileText size={16} className="mr-2 inline" />Markdown</button>
              <button type="button" className={`rounded-xl border px-4 py-3 text-sm ${format === 'html' ? 'border-brand bg-active text-text' : 'border-border text-text-2'}`} onClick={() => setFormat('html')}><Globe2 size={16} className="mr-2 inline" />HTML</button>
            </div>
          </label>

          <label className="flex items-center justify-between gap-4 text-sm text-text">
            <span className="flex items-center gap-3"><Layers3 size={16} /> {t('publish.includeAppendices', 'Include appendices')}</span>
            <input type="checkbox" checked={includeAppendices} onChange={(event) => setIncludeAppendices(event.target.checked)} data-testid="publish-appendices-toggle" />
          </label>

          {scope === 'chapter' && (
            <div>
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('publish.selectChapters', 'Select chapters')}</div>
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
            <span className="flex items-center gap-3"><Download size={18} /> {t('publish.generateExport', 'Generate export')}</span>
            <span className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{format}</span>
          </button>
        </div>

        <div className="mt-8 rounded-2xl border border-border bg-card p-5 shadow-1" data-testid="publish-export-history">
          <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('publish.generatedExports', 'Generated Exports')}</div>
          <div className="space-y-3">
            {exports.length > 0 ? exports.map((artifact) => (
              <div key={artifact.id} className="rounded-xl border border-border bg-bg p-3">
                <div className="text-sm font-bold text-text">{artifact.fileName}</div>
                <div className="mt-1 text-[11px] text-text-3">{artifact.path || 'In-memory preview'}</div>
                <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">{artifact.scope} {artifact.chapterIds?.length ? `/${artifact.chapterIds.length} chapters` : ''}</div>
              </div>
            )) : <div className="text-sm text-text-3">{t('publish.none', 'No exports yet.')}</div>}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8" data-testid="publish-preview-panel">
        <div className="mb-4 flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">
          <ScrollText size={14} /> {t('publish.preview', 'Preview')}
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
