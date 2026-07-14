import { useEffect } from 'react';
import { useProjectStore } from '../store';

const isEditable = (element: Element | null) => element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || (element instanceof HTMLElement && element.isContentEditable);
let shortcutOwnerCount = 0;

const onUndoShortcut = (event: KeyboardEvent) => {
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'z' || isEditable(document.activeElement)) return;

  // Capture ownership prevents feature-local bubble listeners from replaying this command.
  event.preventDefault();
  event.stopImmediatePropagation();
  const store = useProjectStore.getState();
  if (event.shiftKey) void store.redoAction();
  else void store.undoAction();
};

/** Global structured-data undo. Text editors retain ownership of their native undo. */
export const useCommandShortcuts = () => {
  useEffect(() => {
    if (shortcutOwnerCount++ === 0) window.addEventListener('keydown', onUndoShortcut, true);
    return () => {
      shortcutOwnerCount -= 1;
      if (shortcutOwnerCount === 0) window.removeEventListener('keydown', onUndoShortcut, true);
    };
  }, []);
};
