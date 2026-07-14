import type { AppCommand, CommandContext } from './types';

export const toMenuItem = <T extends CommandContext>(command: AppCommand<T>, context: T) => ({
  id: command.id,
  label: command.label,
  shortcut: command.shortcut,
  destructive: command.destructive,
  disabled: command.disabled,
  disabledReason: command.disabledReason,
  action: () => command.execute(context),
});
