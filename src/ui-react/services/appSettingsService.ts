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
  ],
  selectedProviderProfileId: 'provider_openai_default',
  selectedModelProfileId: 'model_default_story',
};

export const appSettingsService = {
  async load(): Promise<AppSettings> {
    const fromElectron = await electronApi.loadAppSettings<AppSettings>();
    if (fromElectron) {
      return { ...defaultAppSettings, ...fromElectron };
    }
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...defaultAppSettings, ...(JSON.parse(raw) as AppSettings) } : defaultAppSettings;
  },

  async save(partial: Partial<AppSettings>): Promise<AppSettings> {
    const current = await this.load();
    const next = { ...current, ...partial };
    const saved = await electronApi.saveAppSettings<AppSettings>(next);
    if (saved) {
      return { ...defaultAppSettings, ...saved };
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
  },
};
