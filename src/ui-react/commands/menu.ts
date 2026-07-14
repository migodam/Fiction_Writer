import type { AppCommand, CommandContext } from "./types";

type Translate = (key: string, fallback: string) => string;

export const toMenuItem = <T extends CommandContext>(
  command: AppCommand<T>,
  context: T,
  t: Translate,
) => ({
  id: command.id,
  label: t(command.label.key, command.label.fallback),
  shortcut: command.shortcut,
  destructive: command.destructive,
  disabled: command.disabled,
  disabledReason:
    command.disabledReason &&
    t(command.disabledReason.key, command.disabledReason.fallback),
  action: () => command.execute(context),
});
