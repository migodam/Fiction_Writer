import React, { useEffect, useRef, useState } from 'react';
import { Settings, X } from 'lucide-react';
import { cn } from '../../utils';
import { useI18n } from '../../i18n';
import { electronApi } from '../../services/electronApi';

export interface AIWritingModalProps {
  mode: 'continue' | 'polish';
  sceneTitle: string;
  existingContent: string;
  onAccept: (newContent: string) => void;
  onClose: () => void;
}

interface AIWritingConfig {
  style: 'narrative' | 'cinematic' | 'poetic' | 'minimal';
  tone: 'neutral' | 'dark' | 'hopeful' | 'tense' | 'humorous';
  length: 'short' | 'medium' | 'long';
  custom: string;
}

const CONFIG_KEY = 'aiWriting.config';

const defaultConfig: AIWritingConfig = {
  style: 'narrative',
  tone: 'neutral',
  length: 'medium',
  custom: '',
};

const loadConfig = (): AIWritingConfig => {
  try {
    const raw = localStorage.getItem(CONFIG_KEY);
    if (raw) return { ...defaultConfig, ...JSON.parse(raw) };
  } catch {
    // ignore parse errors
  }
  return defaultConfig;
};

const saveConfig = (config: AIWritingConfig) => {
  try {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
  } catch {
    // ignore storage errors
  }
};

const buildPrompt = (
  mode: 'continue' | 'polish',
  config: AIWritingConfig,
  sceneTitle: string,
  content: string
): string => {
  const styleInst = config.style !== 'narrative' ? `Style: ${config.style}.` : '';
  const toneInst = config.tone !== 'neutral' ? `Tone: ${config.tone}.` : '';
  const customInst = config.custom ? `Additional instructions: ${config.custom}` : '';

  if (mode === 'continue') {
    const lengthInst =
      { short: 'Write 1-2 paragraphs.', medium: 'Write 3-4 paragraphs.', long: 'Write 5+ paragraphs.' }[
        config.length
      ] ?? '';
    return `You are a creative fiction writing assistant. Continue the following scene titled "${sceneTitle}". ${styleInst} ${toneInst} ${lengthInst} ${customInst}\n\nScene so far:\n${content}\n\nContinue:`;
  } else {
    return `You are a creative fiction writing assistant. Polish and improve the following scene titled "${sceneTitle}". ${styleInst} ${toneInst} ${customInst} Preserve the author's voice and intent.\n\nScene:\n${content}\n\nPolished version:`;
  }
};

export const AIWritingModal: React.FC<AIWritingModalProps> = ({
  mode,
  sceneTitle,
  existingContent,
  onAccept,
  onClose,
}) => {
  const { t } = useI18n();
  const [config, setConfig] = useState<AIWritingConfig>(loadConfig);
  const [configOpen, setConfigOpen] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [output, setOutput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const cleanupsRef = useRef<Array<() => void>>([]);
  const requestIdRef = useRef<string>('');

  const updateConfig = (partial: Partial<AIWritingConfig>) => {
    const next = { ...config, ...partial };
    setConfig(next);
    saveConfig(next);
  };

  const handleGenerate = () => {
    const requestId = `writing-${Date.now()}`;
    requestIdRef.current = requestId;
    setStreaming(true);
    setDone(false);
    setOutput('');
    setError(null);

    const cleanups = [
      electronApi.onAIChunk(requestId, (text) => setOutput((prev) => prev + text)),
      electronApi.onAIDone(requestId, () => {
        setStreaming(false);
        setDone(true);
      }),
      electronApi.onAIError(requestId, (msg) => {
        setError(msg);
        setStreaming(false);
      }),
    ];
    cleanupsRef.current = cleanups;

    electronApi.aiStreamStart(requestId, [
      { role: 'user', content: buildPrompt(mode, config, sceneTitle, existingContent) },
    ]);
  };

  const handleCancel = () => {
    electronApi.aiStreamCancel(requestIdRef.current);
    cleanupsRef.current.forEach((fn) => fn());
    cleanupsRef.current = [];
    setStreaming(false);
  };

  // Clean up listeners on unmount
  useEffect(() => {
    return () => {
      cleanupsRef.current.forEach((fn) => fn());
    };
  }, []);

  const title = mode === 'continue' ? t('aiWriting.continueTitle') : t('aiWriting.polishTitle');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      data-testid="ai-writing-modal"
    >
      <div className="mx-4 flex w-full max-w-2xl flex-col rounded-[28px] border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="text-base font-black text-text">{title}</div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={cn(
                'rounded-xl border border-border p-2 text-text-2 hover:border-brand',
                configOpen && 'border-brand text-brand'
              )}
              onClick={() => setConfigOpen((v) => !v)}
              aria-label={t('aiWriting.configToggle')}
            >
              <Settings size={15} />
            </button>
            <button
              type="button"
              className="rounded-xl border border-border p-2 text-text-2 hover:border-brand"
              data-testid="ai-writing-close-btn"
              onClick={onClose}
              aria-label={t('aiWriting.close')}
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Config section */}
        {configOpen && (
          <div className="border-b border-border bg-bg-elev-1 px-6 py-4">
            <div className="mb-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">
              {t('aiWriting.configToggle')}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-[11px] font-bold text-text-2">{t('aiWriting.style')}</label>
                <select
                  data-testid="ai-writing-style-select"
                  value={config.style}
                  onChange={(e) => updateConfig({ style: e.target.value as AIWritingConfig['style'] })}
                  className="w-full rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-brand"
                >
                  <option value="narrative">{t('aiWriting.styleNarrative')}</option>
                  <option value="cinematic">{t('aiWriting.styleCinematic')}</option>
                  <option value="poetic">{t('aiWriting.stylePoetic')}</option>
                  <option value="minimal">{t('aiWriting.styleMinimal')}</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-bold text-text-2">{t('aiWriting.tone')}</label>
                <select
                  data-testid="ai-writing-tone-select"
                  value={config.tone}
                  onChange={(e) => updateConfig({ tone: e.target.value as AIWritingConfig['tone'] })}
                  className="w-full rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-brand"
                >
                  <option value="neutral">{t('aiWriting.toneNeutral')}</option>
                  <option value="dark">{t('aiWriting.toneDark')}</option>
                  <option value="hopeful">{t('aiWriting.toneHopeful')}</option>
                  <option value="tense">{t('aiWriting.toneTense')}</option>
                  <option value="humorous">{t('aiWriting.toneHumorous')}</option>
                </select>
              </div>
              {mode === 'continue' && (
                <div>
                  <label className="mb-1 block text-[11px] font-bold text-text-2">{t('aiWriting.length')}</label>
                  <select
                    data-testid="ai-writing-length-select"
                    value={config.length}
                    onChange={(e) => updateConfig({ length: e.target.value as AIWritingConfig['length'] })}
                    className="w-full rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-brand"
                  >
                    <option value="short">{t('aiWriting.lengthShort')}</option>
                    <option value="medium">{t('aiWriting.lengthMedium')}</option>
                    <option value="long">{t('aiWriting.lengthLong')}</option>
                  </select>
                </div>
              )}
            </div>
            <div className="mt-3">
              <textarea
                data-testid="ai-writing-custom-input"
                value={config.custom}
                onChange={(e) => updateConfig({ custom: e.target.value })}
                placeholder={t('aiWriting.customPlaceholder')}
                rows={2}
                className="w-full rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-brand resize-none"
              />
            </div>
          </div>
        )}

        {/* Body */}
        <div className="flex flex-col gap-4 px-6 py-5">
          {/* Generate button */}
          <button
            type="button"
            data-testid="ai-writing-generate-btn"
            disabled={streaming}
            onClick={handleGenerate}
            className={cn(
              'rounded-xl px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white transition-opacity',
              streaming ? 'cursor-not-allowed bg-brand opacity-50' : 'bg-brand hover:opacity-90'
            )}
          >
            {streaming ? t('aiWriting.generating') : t('aiWriting.generate')}
          </button>

          {/* Streaming output */}
          {(output || streaming) && (
            <div
              data-testid="ai-writing-output"
              className="min-h-[120px] max-h-[320px] overflow-y-auto rounded-2xl border border-border bg-bg-elev-1 p-4 text-sm text-text whitespace-pre-wrap custom-scrollbar"
            >
              {output}
              {streaming && (
                <span className="ml-1 inline-block h-3 w-1 animate-pulse bg-brand" />
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {t('aiWriting.error', `Error: ${error}`).replace('{msg}', error)}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex justify-end gap-2">
            {streaming && (
              <button
                type="button"
                data-testid="ai-writing-cancel-btn"
                onClick={handleCancel}
                className="rounded-xl border border-border px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-text-2 hover:border-brand"
              >
                {t('aiWriting.cancel')}
              </button>
            )}
            {done && !streaming && output && (
              <button
                type="button"
                data-testid="ai-writing-accept-btn"
                onClick={() => onAccept(output)}
                className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white hover:opacity-90"
              >
                {t('aiWriting.accept')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
