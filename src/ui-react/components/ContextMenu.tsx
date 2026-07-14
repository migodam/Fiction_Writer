import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useUIStore } from "../store";
import { useI18n } from "../i18n";

const MENU_WIDTH = 240;
const VIEWPORT_GAP = 8;

export const ContextMenu = () => {
  const { contextMenu, closeContextMenu } = useUIStore();
  const { t } = useI18n();
  const menuRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  useLayoutEffect(() => {
    if (!contextMenu) return;
    const height = menuRef.current?.offsetHeight ?? 220;
    setPosition({
      left: Math.max(
        VIEWPORT_GAP,
        Math.min(contextMenu.x, window.innerWidth - MENU_WIDTH - VIEWPORT_GAP),
      ),
      top: Math.max(
        VIEWPORT_GAP,
        Math.min(contextMenu.y, window.innerHeight - height - VIEWPORT_GAP),
      ),
    });
    setActiveIndex(contextMenu.items.findIndex((item) => !item.disabled));
    setConfirmingId(null);
    requestAnimationFrame(() => menuRef.current?.focus());
  }, [contextMenu]);

  useEffect(() => {
    if (!contextMenu) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) closeContextMenu();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeContextMenu();
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [closeContextMenu, contextMenu]);

  if (!contextMenu) return null;
  const close = () => {
    const returnFocus = contextMenu.returnFocus;
    closeContextMenu();
    requestAnimationFrame(() => returnFocus?.focus());
  };
  const run = async (index: number) => {
    const item = contextMenu.items[index];
    if (!item || item.disabled) return;
    if (item.destructive && confirmingId !== item.id) {
      setConfirmingId(item.id);
      return;
    }
    await item.action();
    close();
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const enabled = contextMenu.items
      .map((item, index) => (item.disabled ? -1 : index))
      .filter((index) => index >= 0);
    if (!enabled.length) {
      if (
        event.key === "Enter" ||
        event.key === " " ||
        event.key.startsWith("Arrow") ||
        event.key === "Home" ||
        event.key === "End"
      )
        event.preventDefault();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const current = enabled.indexOf(activeIndex);
      const next =
        event.key === "ArrowDown"
          ? (current + 1) % enabled.length
          : (current - 1 + enabled.length) % enabled.length;
      setActiveIndex(enabled[next]);
    } else if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(enabled[0]);
    } else if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(enabled[enabled.length - 1]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void run(activeIndex);
    }
  };

  return (
    <div
      ref={menuRef}
      role="menu"
      tabIndex={-1}
      onKeyDown={onKeyDown}
      className="context-menu fixed z-[120] w-[240px]"
      style={position}
      data-testid="global-context-menu"
    >
      {contextMenu.items.map((item, index) => {
        const confirming = confirmingId === item.id;
        return (
          <button
            type="button"
            role="menuitem"
            key={item.id}
            data-testid={`context-menu-item-${item.id}`}
            disabled={item.disabled}
            title={item.disabledReason}
            aria-disabled={item.disabled}
            className={`context-menu__item ${item.disabled ? "context-menu__item--disabled" : item.destructive ? "context-menu__item--destructive" : ""} ${index === activeIndex ? "context-menu__item--active" : ""}`}
            onMouseEnter={() => !item.disabled && setActiveIndex(index)}
            onClick={() => void run(index)}
          >
            <span>
              {confirming
                ? t("contextMenu.confirmAction", "Confirm {label}?").replace(
                    "{label}",
                    item.label,
                  )
                : item.label}
            </span>
            <span className="context-menu__meta">
              {item.disabledReason ?? formatShortcut(item.shortcut) ?? ""}
            </span>
          </button>
        );
      })}
    </div>
  );
};

const formatShortcut = (shortcut?: string) => {
  if (!shortcut) return undefined;
  const isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform);
  return isMac
    ? shortcut.replace("Ctrl+", "⌘").replace("Alt+", "⌥").replace("Shift+", "⇧")
    : shortcut;
};
