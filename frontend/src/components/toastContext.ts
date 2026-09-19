import { createContext } from 'react';

export type ToastKind = 'ok' | 'error' | 'info';
export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}
export interface ToastApi {
  push: (text: string, kind?: ToastKind) => void;
}
export const ToastContext = createContext<ToastApi>({ push: () => undefined });
