export type CommandTargetKind =
  | "character"
  | "world-item"
  | "world-folder"
  | "manuscript-node"
  | "timeline-event"
  | "graph-node"
  | "graph-edge";

export interface CommandTarget {
  kind: CommandTargetKind;
  id: string;
}

export interface CommandContext {
  target: CommandTarget;
  selection?: { type: string | null; id: string | null };
  source?: "context-menu" | "keyboard" | "drag";
}

export interface CommandText {
  key: string;
  fallback: string;
}

export interface AppCommand<TContext extends CommandContext = CommandContext> {
  id: string;
  label: CommandText;
  shortcut?: string;
  destructive?: boolean;
  disabled?: boolean;
  disabledReason?: CommandText;
  execute: (context: TContext) => void | Promise<void>;
}

export interface ClipboardEntry<T = unknown> {
  kind: CommandTargetKind;
  operation: "copy" | "cut";
  value: T;
}
