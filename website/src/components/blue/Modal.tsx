import { useEffect, useId, useRef } from 'react';
import { t } from '../../app/i18n';
import type { BlueModalProps } from './types';

// Dialog over the page (BLUE BModal), built on the native <dialog>: the browser keeps the keyboard focus inside it,
// makes the page behind it unusable while it is open and gives the focus back when it closes.
// Esc, the × button and a click on the dark area around it call onClose; the parent decides whether it closes.
export function BlueModal({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  dismissible = true,
  className = '',
}: BlueModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const pressedOutside = useRef(false);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  function requestClose() {
    if (dismissible) onClose();
  }

  return (
    <dialog
      ref={dialogRef}
      className={`blue-modal blue-modal--${size} ${className}`.trim()}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault(); // Esc: let the parent close it, so `open` stays the source of truth
        requestClose();
      }}
      // A click on the dialog element itself is a click on the dark area (the panel covers the rest). Both the press
      // and the release must be there, so selecting text inside and releasing outside does not close it.
      onMouseDown={(event) => {
        pressedOutside.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        if (pressedOutside.current && event.target === event.currentTarget) requestClose();
        pressedOutside.current = false;
      }}
    >
      <div className="blue-modal__panel">
        <header className="blue-modal__header">
          <h2 id={titleId} className="blue-modal__title">
            {title}
          </h2>
          <button
            type="button"
            className="blue-modal__close"
            aria-label={t('blue.close')}
            onClick={requestClose}
            disabled={!dismissible}
          >
            ×
          </button>
        </header>
        <div className="blue-modal__body">{children}</div>
        {footer ? <footer className="blue-modal__footer">{footer}</footer> : null}
      </div>
    </dialog>
  );
}
