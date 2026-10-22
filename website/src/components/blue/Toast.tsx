import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { BlueToastApi, BlueToastOptions, BlueToastProviderProps, BlueToastVariant } from './types';
import { BlueToastContext } from './useBlueToast';
import { t } from '../../app/i18n';

// Shows the toasts asked for with useBlueToast() (BLUE BToast). Put it once around the app.
// Toasts are announced to screen readers (errors right away, others politely) and close by themselves after a
// while, unless hovered or focused. A toast cannot be clicked while a modal dialog is open (the page behind a
// dialog is inert), so show it after the dialog closes; inside a dialog, show the result in the dialog itself.

interface Toast {
  id: number;
  variant: BlueToastVariant;
  title: string;
  message?: ReactNode;
  duration: number;
  action?: { label: string; onClick: () => void };
}

/** Errors stay longer: they usually say what to do next. */
const DEFAULT_DURATION: Record<BlueToastVariant, number> = { info: 4000, success: 4000, warning: 6000, error: 8000 };

export function BlueToastProvider({ children, max = 3 }: BlueToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((toast) => toast.id !== id)), []);

  const show = useCallback(
    ({ variant = 'info', title, message, duration, action }: BlueToastOptions) => {
      const id = nextId.current++;
      const toast = { id, variant, title, message, duration: duration ?? DEFAULT_DURATION[variant], action };
      setToasts((list) => [...list, toast].slice(-max));
      return id;
    },
    [max],
  );

  const api = useMemo<BlueToastApi>(
    () => ({
      show,
      dismiss,
      success: (title, message) => show({ variant: 'success', title, message }),
      error: (title, message) => show({ variant: 'error', title, message }),
      info: (title, message) => show({ variant: 'info', title, message }),
    }),
    [show, dismiss],
  );

  return (
    <BlueToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div className="blue-toast-region" role="region" aria-label={t('blue.notifications')} aria-live="polite">
          {toasts.map((toast) => (
            <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>,
        document.body,
      )}
    </BlueToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const [paused, setPaused] = useState(false);
  const { id, variant, title, message, duration, action } = toast;

  useEffect(() => {
    if (!duration || paused) return;
    const timer = window.setTimeout(() => onDismiss(id), duration);
    return () => window.clearTimeout(timer);
  }, [id, duration, paused, onDismiss]);

  return (
    <div
      className={`blue-toast blue-toast--${variant}`}
      role={variant === 'error' ? 'alert' : 'status'}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <ToastIcon variant={variant} />
      <div className="blue-toast__content">
        <p className="blue-toast__title">{title}</p>
        {message ? <div className="blue-toast__message">{message}</div> : null}
      </div>
      {action ? (
        <button
          type="button"
          className="blue-toast__action"
          onClick={() => {
            onDismiss(id);
            action.onClick();
          }}
        >
          {action.label}
        </button>
      ) : null}
      <button type="button" className="blue-toast__close" aria-label={t('blue.closeNotification')} onClick={() => onDismiss(id)}>
        ×
      </button>
    </div>
  );
}

function ToastIcon({ variant }: { variant: BlueToastVariant }) {
  return (
    <svg className="blue-toast__icon" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="10" />
      {variant === 'success' ? (
        <path d="M5.5 10.5l3 3 6-6.5" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      ) : variant === 'info' ? (
        <path d="M10 9v5M10 6v.01" fill="none" strokeWidth="2" strokeLinecap="round" />
      ) : (
        <path d="M10 5.5v5.5M10 14v.01" fill="none" strokeWidth="2" strokeLinecap="round" />
      )}
    </svg>
  );
}
