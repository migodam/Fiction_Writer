import { appSettingsService } from './appSettingsService';

export interface AITextConfig {
  endpoint: string;
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

export interface AIImageConfig {
  endpoint: string;
  apiKey: string;
  model: string;
  size: string;
}

export async function getActiveTextConfig(): Promise<AITextConfig> {
  const settings = await appSettingsService.load();
  const profiles = settings.providerProfiles ?? [];
  const modelProfiles = settings.modelProfiles ?? [];
  const profile =
    profiles.find((p) => p.id === settings.selectedProviderProfileId) ?? profiles[0];
  const modelProfile =
    modelProfiles.find((m) => m.id === settings.selectedModelProfileId) ?? modelProfiles[0];
  if (!profile) throw new Error('No AI provider configured');
  return {
    endpoint: profile.endpoint,
    apiKey: profile.apiKey,
    model: modelProfile?.model ?? 'gpt-4o-mini',
    temperature: modelProfile?.temperature ?? 0.7,
    maxTokens: (modelProfile as (typeof modelProfile & { maxTokens?: number }))?.maxTokens ?? 2048,
  };
}

export async function getActiveImageConfig(): Promise<AIImageConfig> {
  const settings = await appSettingsService.load();
  const profiles = settings.providerProfiles ?? [];
  const profile =
    profiles.find((p) => p.id === settings.selectedProviderProfileId) ?? profiles[0];
  if (!profile) throw new Error('No AI provider configured');
  return {
    endpoint: profile.endpoint,
    apiKey: profile.apiKey,
    model: (profile as typeof profile & { imageModel?: string }).imageModel ?? 'dall-e-3',
    size: '1024x1024',
  };
}
