import React, { useState, useEffect } from 'react';
import { X, ImageIcon } from 'lucide-react';
import { useI18n } from '../../i18n';
import { electronApi } from '../../services/electronApi';
import type { Character } from '../../models/project';

interface AIPortraitModalProps {
  character: Character;
  projectRoot: string;
  onSave: (portraitUrl: string) => void;
  onClose: () => void;
}

const STYLE_PROMPT_KEY = 'aiPortrait.stylePrompt';

const buildImagePrompt = (character: Character, stylePrompt: string): string => {
  const parts = [
    `Portrait of ${character.name}`,
    character.traits ? character.traits : '',
    character.summary ? character.summary : '',
    stylePrompt || 'detailed character portrait, high quality',
  ].filter(Boolean);
  return parts.join(', ');
};

export const AIPortraitModal: React.FC<AIPortraitModalProps> = ({ character, projectRoot, onSave, onClose }) => {
  const { t } = useI18n();
  const [stylePrompt, setStylePrompt] = useState<string>(() => {
    try {
      return localStorage.getItem(STYLE_PROMPT_KEY) || '';
    } catch {
      return '';
    }
  });
  const [generatedUrl, setGeneratedUrl] = useState<string>('');
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    try {
      localStorage.setItem(STYLE_PROMPT_KEY, stylePrompt);
    } catch {
      // ignore
    }
  }, [stylePrompt]);

  const characterSummaryText = [
    `Name: ${character.name}`,
    character.birthdayText ? `Birthday: ${character.birthdayText}` : '',
    character.traits ? `Traits: ${character.traits}` : '',
    character.goals ? `Goals: ${character.goals}` : '',
    character.fears ? `Fears: ${character.fears}` : '',
    character.speechStyle ? `Speech style: ${character.speechStyle}` : '',
    character.summary ? `Summary: ${character.summary}` : '',
  ].filter(Boolean).join('\n');

  const handleGenerate = async () => {
    setGenerating(true);
    setError('');
    try {
      const prompt = buildImagePrompt(character, stylePrompt);
      const imageUrl = await electronApi.aiGenerateImage(prompt);
      setGeneratedUrl(imageUrl);
    } catch (err) {
      setError(String(err));
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!generatedUrl) return;
    setSaving(true);
    setError('');
    try {
      const fileUrl = await electronApi.portraitSave(projectRoot, character.id, generatedUrl);
      onSave(fileUrl);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      data-testid="ai-portrait-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative mx-4 w-full max-w-lg rounded-3xl border border-border bg-card p-6 shadow-2xl">
        <div className="mb-6 flex items-center justify-between">
          <div className="text-lg font-black text-text">{t('aiPortrait.title')}</div>
          <button
            type="button"
            data-testid="ai-portrait-close-btn"
            className="rounded-xl border border-border p-2 text-text-2 hover:bg-hover"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        <div className="mb-4">
          <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
            {t('aiPortrait.characterSummary')}
          </div>
          <pre className="rounded-2xl border border-border bg-bg-elev-1 p-3 text-xs leading-relaxed text-text-2 whitespace-pre-wrap font-sans">
            {characterSummaryText}
          </pre>
        </div>

        <div className="mb-4">
          <input
            data-testid="ai-portrait-style-input"
            type="text"
            value={stylePrompt}
            onChange={(e) => setStylePrompt(e.target.value)}
            placeholder={t('aiPortrait.stylePlaceholder')}
            className="w-full rounded-2xl border border-border bg-bg px-4 py-3 text-sm outline-none"
          />
        </div>

        {generatedUrl && (
          <div className="mb-4 flex justify-center">
            <img
              data-testid="ai-portrait-preview"
              src={generatedUrl}
              alt="Generated portrait"
              className="max-h-64 rounded-2xl border border-border object-cover"
            />
          </div>
        )}

        {!generatedUrl && !generating && (
          <div className="mb-4 flex h-40 items-center justify-center rounded-2xl border border-border bg-bg-elev-1 text-text-3">
            <div className="flex flex-col items-center gap-2">
              <ImageIcon size={32} />
              <span className="text-sm">{t('aiPortrait.noPortrait')}</span>
            </div>
          </div>
        )}

        {generating && (
          <div className="mb-4 flex h-40 items-center justify-center rounded-2xl border border-border bg-bg-elev-1 text-text-3">
            <div className="flex flex-col items-center gap-2">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" />
              <span className="text-sm">{t('aiPortrait.generating')}</span>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-2xl border border-red/30 bg-red/10 p-3 text-xs text-red">
            {t('aiPortrait.error').replace('{msg}', error)}
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            data-testid="ai-portrait-generate-btn"
            disabled={generating}
            className="flex-1 rounded-xl bg-brand px-4 py-3 text-sm font-black text-white disabled:opacity-50"
            onClick={handleGenerate}
          >
            {generating ? t('aiPortrait.generating') : t('aiPortrait.generate')}
          </button>
          {generatedUrl && (
            <button
              type="button"
              data-testid="ai-portrait-save-btn"
              disabled={saving}
              className="flex-1 rounded-xl border border-border px-4 py-3 text-sm font-black text-text disabled:opacity-50"
              onClick={handleSave}
            >
              {t('aiPortrait.save')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
