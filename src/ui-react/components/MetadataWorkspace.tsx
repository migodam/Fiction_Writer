import React, { useState, useEffect } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { electronApi } from '../services/electronApi';
import type { MetadataFile } from '../models/project';
import { loadChunks } from '../services/metadataService';
import { cn } from '../utils';
import { Upload, Trash2, FileText } from 'lucide-react';

const TYPE_COLORS: Record<string, string> = {
  novel: 'bg-purple-100 text-purple-800',
  article: 'bg-blue-100 text-blue-800',
  script: 'bg-orange-100 text-orange-800',
  essay: 'bg-green-100 text-green-800',
  draft: 'bg-gray-100 text-gray-600',
  other: 'bg-gray-100 text-gray-600',
};

const STATUS_DOT: Record<string, string> = {
  ready: 'bg-green-500',
  processing: 'bg-orange-400',
  error: 'bg-red-500',
};

export const MetadataWorkspace: React.FC = () => {
  const { t } = useI18n();
  const { metadataFiles, projectRoot, loadMetadata, importMetadataFile, deleteMetadataFile } = useProjectStore();
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [chunks, setChunks] = useState<{ id: string; content: string; index: number; tokenCount: number }[]>([]);

  useEffect(() => {
    if (projectRoot) {
      loadMetadata(projectRoot);
    }
  }, [projectRoot, loadMetadata]);

  useEffect(() => {
    if (selectedFileId && projectRoot) {
      const loaded = loadChunks(projectRoot, selectedFileId);
      setChunks(loaded.slice(0, 5));
    } else {
      setChunks([]);
    }
  }, [selectedFileId, projectRoot]);

  const selectedFile = metadataFiles.find((f) => f.id === selectedFileId) ?? null;

  const handleImport = async () => {
    const paths = await electronApi.pickFiles();
    if (!paths.length || !projectRoot) return;
    for (const path of paths) {
      importMetadataFile(projectRoot, path, { type: 'other', tags: [], description: '' });
    }
  };

  const handleDelete = (e: React.MouseEvent, fileId: string) => {
    e.stopPropagation();
    if (!projectRoot) return;
    deleteMetadataFile(projectRoot, fileId);
    if (selectedFileId === fileId) setSelectedFileId(null);
  };

  return (
    <div className="flex h-full" data-testid="metadata-workspace">
      {/* Left pane — file list */}
      <div className="w-72 flex-shrink-0 border-r border-border flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-fg">{t('metadata.title', 'Reference Library')}</h2>
          <button
            className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-brand text-white hover:opacity-90 transition-opacity"
            onClick={handleImport}
            data-testid="metadata-import-btn"
          >
            <Upload size={12} />
            {t('metadata.import', 'Import Files')}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {metadataFiles.length === 0 ? (
            <p className="text-xs text-muted px-4 py-6 text-center">
              {t('metadata.empty', 'No reference files yet. Import .txt or .md files.')}
            </p>
          ) : (
            metadataFiles.map((file) => (
              <div
                key={file.id}
                className={cn(
                  'group flex items-start gap-2 px-3 py-2 cursor-pointer border-b border-border/50 hover:bg-surface-hover transition-colors',
                  selectedFileId === file.id && 'bg-surface-active'
                )}
                onClick={() => setSelectedFileId(file.id)}
                data-testid={`metadata-file-item-${file.id}`}
              >
                <div className="mt-0.5 flex-shrink-0">
                  <FileText size={14} className="text-muted" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span
                      className={cn(
                        'inline-block w-1.5 h-1.5 rounded-full flex-shrink-0',
                        STATUS_DOT[file.status] ?? 'bg-gray-400'
                      )}
                    />
                    <span className="text-xs font-medium text-fg truncate">{file.filename}</span>
                  </div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={cn(
                        'inline-block text-xs px-1 py-0 rounded font-medium',
                        TYPE_COLORS[file.type] ?? TYPE_COLORS.other
                      )}
                    >
                      {t(`metadata.type.${file.type}`, file.type)}
                    </span>
                    <span className="text-xs text-muted">
                      {file.chunkCount} {t('metadata.chunkCount', 'chunks')}
                    </span>
                  </div>
                  {file.tags.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {file.tags.map((tag) => (
                        <span key={tag} className="text-xs bg-surface text-muted px-1 rounded">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  className="flex-shrink-0 p-1 text-muted hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => handleDelete(e, file.id)}
                  data-testid={`metadata-delete-btn-${file.id}`}
                  title={t('metadata.delete', 'Delete')}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right pane — detail and chunks */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {!selectedFile ? (
          <p className="text-sm text-muted mt-8 text-center">
            {t('metadata.noChunks', 'Select a file to preview chunks.')}
          </p>
        ) : (
          <>
            <div className="mb-4">
              <h3 className="text-base font-semibold text-fg mb-1">{selectedFile.filename}</h3>
              {selectedFile.description && (
                <p className="text-sm text-muted mb-2">{selectedFile.description}</p>
              )}
              <div className="flex items-center gap-2 text-xs text-muted">
                <span
                  className={cn(
                    'inline-block px-1 py-0 rounded font-medium',
                    TYPE_COLORS[selectedFile.type] ?? TYPE_COLORS.other
                  )}
                >
                  {t(`metadata.type.${selectedFile.type}`, selectedFile.type)}
                </span>
                <span>
                  {selectedFile.chunkCount} {t('metadata.chunkCount', 'chunks')}
                </span>
                <span>{new Date(selectedFile.importedAt).toLocaleDateString()}</span>
              </div>
            </div>

            <h4 className="text-sm font-medium text-fg mb-2">{t('metadata.chunks', 'Chunks Preview')}</h4>
            {chunks.length === 0 ? (
              <p className="text-xs text-muted">{t('metadata.noChunks', 'Select a file to preview chunks.')}</p>
            ) : (
              <div className="space-y-3">
                {chunks.map((chunk) => (
                  <div key={chunk.id} className="rounded border border-border bg-surface p-3">
                    <div className="text-xs text-muted mb-1">
                      Chunk {chunk.index + 1} &mdash; {chunk.tokenCount} tokens
                    </div>
                    <pre className="text-xs text-fg whitespace-pre-wrap font-mono leading-relaxed">
                      {chunk.content}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default MetadataWorkspace;
