import type { AppSettings } from '../models/project';
import { electronApi } from './electronApi';

const STORAGE_KEY = 'narrative-ide-app-settings';

export const defaultAppSettings: AppSettings = {
  locale: 'en',
  density: 'comfortable',
  editorWidth: 'focused',
  motionLevel: 'full',
  theme: 'dark',
  defaultExportFormat: 'markdown',
  defaultChapterExportScope: 'chapter',
  providerProfiles: [
    {
      id: 'provider_openai_default',
      provider: 'openai',
      label: 'OpenAI Default',
      endpoint: 'https://api.openai.com/v1',
      apiKey: '',
      enabled: false,
    },
    {
      id: 'provider_deepseek_default',
      provider: 'deepseek',
      label: 'DeepSeek',
      endpoint: 'https://api.deepseek.com/v1',
      apiKey: '',
      enabled: false,
    },
  ],
  modelProfiles: [
    {
      id: 'model_default_story',
      label: 'Story Drafting',
      model: 'gpt-4.1',
      temperature: 0.8,
      topP: 1,
      useCase: 'writing',
    },
    {
      id: 'model_deepseek_v4_pro',
      label: 'DeepSeek V4 Pro',
      model: 'deepseek-v4-pro',
      temperature: 0.7,
      topP: 1,
      useCase: 'general',
    },
    {
      id: 'model_deepseek_v4_flash',
      label: 'DeepSeek V4 Flash',
      model: 'deepseek-v4-flash',
      temperature: 0.7,
      topP: 1,
      useCase: 'general',
    },
  ],
  selectedProviderProfileId: 'provider_openai_default',
  selectedModelProfileId: 'model_default_story',
};

// Merge saved array with defaults — any default entry missing from saved is appended.
// This ensures new defaults survive settings file resets without overwriting user edits.
function mergeById<T extends { id: string }>(defaults: T[], saved: T[]): T[] {
  const savedIds = new Set(saved.map((x) => x.id));
  return [...saved, ...defaults.filter((d) => !savedIds.has(d.id))];
}

function mergeWithDefaults(saved: AppSettings): AppSettings {
  return {
    ...defaultAppSettings,
    ...saved,
    providerProfiles: mergeById(defaultAppSettings.providerProfiles, saved.providerProfiles ?? []),
    modelProfiles: mergeById(defaultAppSettings.modelProfiles, saved.modelProfiles ?? []),
  };
}

export const appSettingsService = {
  async load(): Promise<AppSettings> {
    const fromElectron = await electronApi.loadAppSettings<AppSettings>();
    if (fromElectron) {
      return mergeWithDefaults(fromElectron);
    }
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? mergeWithDefaults(JSON.parse(raw) as AppSettings) : defaultAppSettings;
  },

  async save(partial: Partial<AppSettings>): Promise<AppSettings> {
    const current = await this.load();
    const next = { ...current, ...partial };
    const saved = await electronApi.saveAppSettings<AppSettings>(next);
    if (saved) {
      return mergeWithDefaults(saved);
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
  },
};
