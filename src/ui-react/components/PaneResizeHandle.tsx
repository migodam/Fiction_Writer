import React from 'react';
import { useUIStore } from '../store';
import { cn } from '../utils';

type PanelKind = 'sidebar' | 'inspector' | 'agentDock' | 'writingOutline' | 'writingContext';

export const PaneResizeHandle = ({
  panel,
  className,
  direction = 'left',
  testId,
}: {
  panel: PanelKind;
  className?: string;
  direction?: 'left' | 'right';
  testId?: string;
}) => {
  const setPanelWidth = useUIStore((state) => state.setPanelWidth);

  const handleMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const state = useUIStore.getState();
    const currentWidth =
      panel === 'sidebar' ? state.sidebarWidth :
      panel === 'inspector' ? state.inspectorWidth :
      panel === 'agentDock' ? state.agentDockWidth :
      panel === 'writingOutline' ? state.writingOutlineWidth :
      state.writingContextWidth;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      setPanelWidth(panel, direction === 'left' ? currentWidth - delta : currentWidth + delta);
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  return (
    <div
      className={cn('relative w-1.5 cursor-col-resize bg-transparent', className)}
      onMouseDown={handleMouseDown}
      data-testid={testId || `${panel}-resizer`}
    >
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-white/7 transition-colors hover:bg-amber-300/70" />
    </div>
  );
};
