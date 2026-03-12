import React, { useEffect } from 'react';
import { useUIStore } from '../store';

export const ContextMenu = () => {
  const { contextMenu, closeContextMenu } = useUIStore();

  useEffect(() => {
    if (!contextMenu) return;
    const handleClose = () => closeContextMenu();
    window.addEventListener('click', handleClose);
    window.addEventListener('contextmenu', handleClose);
    window.addEventListener('keydown', handleClose);
    return () => {
      window.removeEventListener('click', handleClose);
      window.removeEventListener('contextmenu', handleClose);
      window.removeEventListener('keydown', handleClose);
    };
  }, [closeContextMenu, contextMenu]);

  if (!contextMenu) return null;

  return (
    <div
      className="fixed z-[120] min-w-[220px] overflow-hidden rounded-2xl border border-white/10 bg-slate-950/95 p-2 shadow-[0_24px_60px_rgba(0,0,0,0.5)] backdrop-blur"
      style={{ left: contextMenu.x, top: contextMenu.y }}
      data-testid="global-context-menu"
    >
      {contextMenu.items.map((item) => (
        <button
          type="button"
          key={item.id}
          className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition-colors ${item.destructive ? 'text-red-300 hover:bg-red-500/10' : 'text-slate-100 hover:bg-white/6'}`}
          onClick={() => {
            item.action();
            closeContextMenu();
          }}
        >
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
};
