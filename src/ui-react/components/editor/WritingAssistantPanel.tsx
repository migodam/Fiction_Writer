import React from 'react';

interface WritingAssistantPanelProps {
  w3Status: 'idle' | 'running' | 'waiting_selection' | 'done' | 'error';
  w3Options: string[];
  w3Output: string;
  w3Progress: number;
  w3Error: string | null;
  task: string;
  onTaskChange: (task: string) => void;
  onGenerate: () => void;
  onSelectOption: (index: number) => void;
  onInsert: (text: string) => void;
  onRetry: () => void;
}

export const WritingAssistantPanel: React.FC<WritingAssistantPanelProps> = ({
  w3Status,
  w3Options,
  w3Output,
  w3Progress,
  w3Error,
  task,
  onTaskChange,
  onGenerate,
  onSelectOption,
  onInsert,
  onRetry,
}) => {
  return (
    <div className="flex flex-col gap-3 p-4 border-l border-border bg-bg-elev-1 w-72 overflow-y-auto">
      <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">AI Assistant</div>

      {/* Task selector */}
      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-text-2">Task</label>
        <select
          data-testid="w3-task-select"
          value={task}
          onChange={(e) => onTaskChange(e.target.value)}
          className="rounded border border-border bg-bg px-2 py-1 text-sm text-text"
        >
          <option value="continue">Continue</option>
          <option value="rewrite">Rewrite</option>
          <option value="expand">Expand</option>
          <option value="improve_dialogue">Improve Dialogue</option>
        </select>
      </div>

      {/* Generate button */}
      <button
        data-testid="w3-generate-btn"
        onClick={onGenerate}
        disabled={w3Status === 'running'}
        className="rounded bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        {w3Status === 'running' ? 'Generating…' : 'Generate'}
      </button>

      {/* Progress bar */}
      {w3Status === 'running' && (
        <div className="h-1 w-full overflow-hidden rounded bg-bg-elev-2">
          <div
            data-testid="w3-progress-bar"
            className="h-full rounded bg-brand transition-all duration-300"
            style={{ width: `${w3Progress * 100}%` }}
          />
        </div>
      )}

      {/* Three option cards */}
      {w3Status === 'waiting_selection' && (
        <div className="flex flex-col gap-2">
          <div className="text-[11px] text-text-2">Choose a direction:</div>
          {w3Options.map((opt, i) => (
            <div
              key={i}
              data-testid={`w3-option-${i}`}
              className="rounded border border-border p-3 text-sm"
            >
              <p className="mb-2 text-text-2 leading-relaxed">
                {opt.slice(0, 200)}{opt.length > 200 ? '…' : ''}
              </p>
              <button
                data-testid={`w3-select-${i}`}
                onClick={() => onSelectOption(i)}
                className="rounded bg-bg-elev-2 px-2 py-1 text-xs text-text hover:bg-hover"
              >
                Select
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Output section */}
      {w3Status === 'done' && (
        <div data-testid="w3-output" className="flex flex-col gap-2">
          <div className="text-[11px] text-text-2">Generated output:</div>
          <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded border border-border bg-bg p-2 text-xs text-text-2 leading-relaxed">
            {w3Output.slice(0, 400)}{w3Output.length > 400 ? '…' : ''}
          </pre>
          <div className="flex gap-2">
            <button
              data-testid="w3-insert-btn"
              onClick={() => onInsert(w3Output)}
              className="flex-1 rounded bg-brand px-2 py-1.5 text-xs font-medium text-white"
            >
              Insert at cursor
            </button>
            <button
              data-testid="w3-retry-btn"
              onClick={onRetry}
              className="rounded border border-border px-2 py-1.5 text-xs text-text-2 hover:bg-hover"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Error section */}
      {w3Status === 'error' && (
        <div data-testid="w3-error" className="flex flex-col gap-2">
          <p className="text-xs text-red-400">{w3Error ?? 'An error occurred'}</p>
          <button
            data-testid="w3-retry-btn"
            onClick={onRetry}
            className="rounded border border-border px-2 py-1.5 text-xs text-text-2 hover:bg-hover"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
};
