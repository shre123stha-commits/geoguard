import { useContext } from 'react';
import { ToastContext } from './toastContext';

/** `const toast = useToast(); toast('Saved.'); toast(msg, 'error')` */
export const useToast = () => useContext(ToastContext).push;
