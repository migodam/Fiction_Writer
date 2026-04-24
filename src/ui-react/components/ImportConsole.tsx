import React, { useRef, useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, Pause, Play, RotateCcw } from 'lucide-react';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';
import type { ChunkLogEntry } from '../services/electronApi';

interface ImportConsoleProps {
  visible: boolean;
}

export const ImportConsole: React.FC<ImportConsoleProps> = ({ visible }) => {
  const { t } = useI18n();
  const w1ConsoleLog = useProjectStore((s) => s.w1ConsoleLog);
  const w1Paused = useProjectStore((s) => s.w1Paused);
  const w1BreakpointChunk = useProjectStore((s) => s.w1BreakpointChunk);
  const w1TotalChunks = useProjectStore((s) => s.w1TotalChunks);
  const setW1Breakpoint = useProjectStore((s) => s.setW1Breakpoint);
  const resumeW1 = useProjectStore((s) => s.resumeW1);
  const rewindW1 = useProjectStore((s) => s.rewindW1);

  const [breakpointInput, setBreakpointInput] = useState('');
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());
  const logEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom as new entries arrive
  useEffect(() => {
    if (visible && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [w1ConsoleLog.length, visible]);

  const handleSetBreakpoint = () => {
    const val = parseInt(breakpointInput, 10);
    if (!isNaN(val) && val > 0) {
      setW1Breakpoint(val);
    }
  };

  const handleClearBreakpoint = () => {
    setBreakpointInput('');
    setW1Breakpoint(null);
  };

  const toggleExpand = (chunkId: number) => {
    setExpandedChunks((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  };

  if (!visible) return null;

  const reversedLog = [...w1ConsoleLog].reverse();

  return (
    <div className="border-t border-border bg-bg-elev-2" data-testid="import-console">
      {/* Breakpoint + pause controls */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border">
        <span className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
          {t('console.breakpoint', 'Breakpoint')}
        </span>
        <input
          type="number"
          min={1}
          max={w1TotalChunks || 9999}
          placeholder={t('console.chunkNumber', 'chunk #')}
          value={breakpointInput}
          onChange={(e) => setBreakpointInput(e.target.value)}
          data-testid="console-breakpoint-input"
          className="w-20 rounded border border-border bg-bg px-2 py-1 text-xs text-text outline-none"
        />
        <button
          type="button"
          data-testid="console-set-breakpoint-btn"
          onClick={handleSetBreakpoint}
          className="rounded border border-border px-2 py-1 text-[10px] font-black uppercase tracking-widest text-text-2 hover:bg-hover"
        >
          {t('console.set', 'Set')}
        </button>
        <button
          type="button"
          data-testid="console-clear-breakpoint-btn"
          onClick={handleClearBreakpoint}
          className="rounded border border-border px-2 py-1 text-[10px] font-black uppercase tracking-widest text-text-2 hover:bg-hover"
        >
          {t('console.clear', 'Clear')}
        </button>
        {w1BreakpointChunk !== null && (
          <span className="text-xs text-brand-2">
            {t('console.breakpointActive', 'Active at chunk')} {w1BreakpointChunk}
          </span>
        )}
      </div>

      {/* Paused banner */}
      {w1Paused && (
        <div className="flex items-center justify-between bg-brand/10 border-b border-brand/20 px-4 py-2">
          <div className="flex items-center gap-2">
            <Pause size={14} className="text-brand" />
            <span className="text-xs font-black uppercase tracking-widest text-brand">
              {t('console.paused', 'Paused')}
            </span>
          </div>
          <button
            type="button"
            data-testid="console-resume-btn"
            onClick={resumeW1}
            className="inline-flex items-center gap-1 rounded bg-brand px-3 py-1 text-[10px] font-black uppercase tracking-widest text-text-invert hover:bg-brand/90"
          >
            <Play size={11} />
            {t('console.resume', 'Resume')}
          </button>
        </div>
      )}

      {/* Log entries */}
      <div className="h-48 overflow-y-auto custom-scrollbar" data-testid="console-log-list">
        {reversedLog.length === 0 && (
          <div className="px-4 py-6 text-center text-xs text-text-3">
            {t('console.waiting', 'Waiting for chunks…')}
          </div>
        )}
        {reversedLog.map((entry: ChunkLogEntry) => {
          const isExpanded = expandedChunks.has(entry.chunk_id);
          const hasErrors = entry.errors.length > 0;
          return (
            <div
              key={`${entry.chunk_id}-${entry.timestamp}`}
              className={`border-b border-border/50 ${hasErrors ? 'bg-red/5' : ''}`}
              data-testid={`console-chunk-${entry.chunk_id}`}
            >
              <div className="flex items-start gap-0">
                {/* Chunk number */}
                <div className="w-12 shrink-0 px-2 py-2 text-right text-[10px] font-black text-text-3">
                  #{entry.chunk_id}
                </div>
                {/* Content */}
                <div className="flex-1 px-2 py-2">
                  <div className="flex items-center gap-3 text-[10px] text-text-2">
                    {entry.new_characters > 0 && (
                      <span className="text-brand-2">
                        {entry.new_characters} {t('console.chars', 'chars')}
                      </span>
                    )}
                    {entry.updated_characters > 0 && (
                      <span className="text-text-3">
                        +{entry.updated_characters} {t('console.updates', 'updates')}
                      </span>
                    )}
                    {entry.new_events > 0 && (
                      <span className="text-green">
                        {entry.new_events} {t('console.events', 'events')}
                      </span>
                    )}
                    {entry.new_world > 0 && (
                      <span className="text-text-3">
                        {entry.new_world} {t('console.world', 'world')}
                      </span>
                    )}
                    <span className="ml-auto text-text-3">{entry.duration_ms}ms</span>
                  </div>
                  {isExpanded && entry.excerpt && (
                    <div className="mt-1 rounded bg-bg px-2 py-1.5 font-mono text-[10px] text-text-2 leading-relaxed line-clamp-3">
                      {entry.excerpt}
                    </div>
                  )}
                  {hasErrors && (
                    <div className="mt-1 text-[10px] text-red">{entry.errors[0]}</div>
                  )}
                </div>
                {/* Actions */}
                <div className="flex items-center gap-1 px-2 py-2 shrink-0">
                  <button
                    type="button"
                    title={t('console.expandExcerpt', 'Preview excerpt')}
                    onClick={() => toggleExpand(entry.chunk_id)}
                    className="rounded p-0.5 text-text-3 hover:bg-hover hover:text-text"
                  >
                    {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                  </button>
                  <button
                    type="button"
                    title={t('console.rewindTo', 'Rewind to this chunk')}
                    data-testid={`console-rewind-${entry.chunk_id}`}
                    onClick={() => rewindW1(entry.chunk_id)}
                    className="rounded p-0.5 text-text-3 hover:bg-hover hover:text-text"
                  >
                    <RotateCcw size={11} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
