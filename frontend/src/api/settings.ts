import { apiFetch } from './client';
import type { Confidence } from './detections';

export type AlertProvider = 'console' | 'telegram' | 'email';

export interface AlertSettings {
  enabled: boolean;
  provider: AlertProvider;
  recipients: string[];
  min_confidence: Confidence;
  min_persistence: number;
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

/** Channels offered in the UI. Telegram exists server-side but is not offered here. */
export const PROVIDER_LABEL: Partial<Record<AlertProvider, string>> = {
  email: 'E-mail',
  console: 'Server log only',
};
export const RECIPIENT_HINT: Record<AlertProvider, string> = {
  console: 'No recipients needed; each alert is written to the server log.',
  telegram: 'Telegram chat IDs (a person or a group the bot has been added to), one per line.',
  email: 'E-mail addresses, one per line.',
};

export interface Insights {
  reviewed: number;
  confirmed: number;
  dismissed: number;
  by_class: {
    confidence: Confidence;
    confirmed: number;
    dismissed: number;
    precision: number | null;
  }[];
  dismiss_reasons: Record<string, number>;
  suggestions: {
    param: string;
    current: number;
    suggested: number;
    keeps_confirmed: number;
    drops_dismissed: number;
    of_confirmed: number;
    of_dismissed: number;
    text: string;
  }[];
  note: string;
  min_labels: number;
}
export const getInsights = () => apiFetch<Insights>('settings/insights');
