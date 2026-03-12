import React, { useState } from 'react';
import { Download, FileText, Globe2, Layers3, ScrollText } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { projectService } from '../services/projectService';
import { useI18n } from '../i18n';

export const PublishWorkspace = () => {
  const { currentProject, addExportArtifact, exports } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const [includeAppendices, setIncludeAppendices] = useState(true);

  const handleExport = (format: 'markdown' | 'html') => {
    if (!currentProject) {
      return;
    }
    const artifact = projectService.exportProject(currentProject, { format, includeAppendices });
    addExportArtifact(artifact);
    setLastActionStatus(`${format.toUpperCase()} ${t('shell.saved')}`);
  };

  const previewSource = currentProject
    ? projectService.renderExport(currentProject, {
        format: 'markdown',
        includeAppendices,
      })
    : '';

  return (
    <div className="flex h-full overflow-hidden bg-bg" data-testid="publish-workspace">
      <div className="w-80 border-r border-border bg-bg-elev-1 p-6" data-testid="publish-controls">
        <div className="mb-8">
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('publish.title')}</div>
          <h1 className="mt-3 text-3xl font-black text-text">{currentProject?.metadata.name}</h1>
          <p className="mt-3 text-sm leading-relaxed text-text-2">{t('publish.body')}</p>
        </div>

        <div className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-1">
          <label className="flex items-center justify-between gap-4 text-sm text-text">
            <span className="flex items-center gap-3"><Layers3 size={16} /> {t('publish.appendices')}</span>
            <input
              type="checkbox"
              checked={includeAppendices}
              onChange={(event) => setIncludeAppendices(event.target.checked)}
              data-testid="publish-appendices-toggle"
            />
          </label>

          <button
            type="button"
            className="flex w-full items-center justify-between rounded-xl border border-border px-4 py-3 text-left text-text transition-colors hover:border-brand"
            onClick={() => handleExport('markdown')}
            data-testid="publish-export-markdown"
          >
            <span className="flex items-center gap-3"><FileText size={18} /> {t('publish.markdown')}</span>
            <Download size={14} />
          </button>

          <button
            type="button"
            className="flex w-full items-center justify-between rounded-xl border border-border px-4 py-3 text-left text-text transition-colors hover:border-brand"
            onClick={() => handleExport('html')}
            data-testid="publish-export-html"
          >
            <span className="flex items-center gap-3"><Globe2 size={18} /> {t('publish.html')}</span>
            <Download size={14} />
          </button>
        </div>

        <div className="mt-8 rounded-2xl border border-border bg-card p-5 shadow-1" data-testid="publish-export-history">
          <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('publish.history')}</div>
          <div className="space-y-3">
            {exports.length > 0 ? (
              exports.map((artifact) => (
                <div key={artifact.id} className="rounded-xl border border-border bg-bg p-3">
                  <div className="text-sm font-bold text-text">{artifact.fileName}</div>
                  <div className="mt-1 text-[11px] text-text-3">{artifact.path || 'In-memory preview'}</div>
                </div>
              ))
            ) : (
              <div className="text-sm text-text-3">{t('publish.none')}</div>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8" data-testid="publish-preview-panel">
        <div className="mb-4 flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">
          <ScrollText size={14} /> {t('publish.preview')}
        </div>
        <pre className="whitespace-pre-wrap rounded-2xl border border-border bg-card p-6 text-sm leading-relaxed text-text-2 shadow-1">
          {previewSource}
        </pre>
      </div>
    </div>
  );
};
