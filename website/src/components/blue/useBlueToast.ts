import { createContext, useContext } from 'react';
import type { BlueToastApi } from './types';

/** Filled by <BlueToastProvider> (Toast.tsx). */
export const BlueToastContext = createContext<BlueToastApi | null>(null);

/**
 * Short notifications in the corner of the screen (BLUE BToast), e.g. to confirm that something was saved:
 *   const toast = useBlueToast();
 *   toast.success("Comment posted");
 * Needs <BlueToastProvider> around the app (main.tsx).
 */
export function useBlueToast(): BlueToastApi {
  const toast = useContext(BlueToastContext);
  if (!toast) throw new Error('useBlueToast() needs a <BlueToastProvider> around the app.');
  return toast;
}
