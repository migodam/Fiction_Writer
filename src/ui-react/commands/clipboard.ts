import type { ClipboardEntry, CommandTargetKind } from './types';

let entry: ClipboardEntry | null = null;

export const commandClipboard = {
  set<T>(kind: CommandTargetKind, operation: ClipboardEntry<T>['operation'], value: T) {
    entry = { kind, operation, value };
  },
  get<T>(kind?: CommandTargetKind): ClipboardEntry<T> | null {
    if (!entry || (kind && entry.kind !== kind)) return null;
    return entry as ClipboardEntry<T>;
  },
  clear() {
    entry = null;
  },
};
