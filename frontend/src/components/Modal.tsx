import { useEffect, useRef, type ReactNode } from 'react';
import { Button } from './ui';

/** Confirm/detail modal per 04-design §6: panel + blur, Esc closes, focus moves inside. */
export function Modal({
  open,
  title,
  children,
  onClose,
  footer,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    const first = ref.current?.querySelector<HTMLElement>(
      'input,select,textarea,button:not([data-close])',
    );
    first?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(13,11,9,.6)] p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-lg rounded-card border border-hair bg-[rgba(13,11,9,.92)] p-6 backdrop-blur-xl"
      >
        <h2 className="text-[20px] font-medium tracking-[-0.02em]">{title}</h2>
        <div className="mt-4">{children}</div>
        <div className="mt-6 flex justify-end gap-2">
          <Button data-close onClick={onClose} variant="ghost">
            Cancel
          </Button>
          {footer}
        </div>
      </div>
    </div>
  );
}

export function ConfirmModal({
  open,
  title,
  text,
  confirmLabel = 'Confirm',
  danger,
  busy,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  text: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <Button variant={danger ? 'danger' : 'primary'} busy={busy} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      }
    >
      <div className="text-[15px] text-soft">{text}</div>
    </Modal>
  );
}
