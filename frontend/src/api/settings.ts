import { apiFetch } from './client';
import type { Confidence } from './detections';

export type AlertProvider = 'console' | 'telegram' | 'email';

export interface AlertSettings {
  enabled: boolean;
  provider: AlertProvider;
  recipients: string[];
  min_confidence: Confidence;
  app_url: string;
}

export interface AlertSettingsOut extends AlertSettings {
  provider_issue: string | null;
  available_providers: AlertProvider[];
}

export const getAlertSettings = () => apiFetch<AlertSettingsOut>('settings/alerts');
export const putAlertSettings = (body: AlertSettings) =>
  apiFetch<AlertSettingsOut>('settings/alerts', { method: 'PUT', body: JSON.stringify(body) });
export const testAlert = (recipient: string) =>
  apiFetch<undefined>('settings/alerts/test', {
    method: 'POST',
    body: JSON.stringify({ recipient }),
  });

export const PROVIDER_LABEL: Record<AlertProvider, string> = {
  console: 'Server log only',
  telegram: 'Telegram bot',
  email: 'E-mail (SMTP)',
};
export const RECIPIENT_HINT: Record<AlertProvider, string> = {
  console: 'No recipients needed; each alert is written to the server log.',
  telegram: 'Telegram chat IDs (a person or a group the bot has been added to), one per line.',
  email: 'E-mail addresses, one per line.',
};
