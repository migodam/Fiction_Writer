import type { ChunkLogEntry, W1ActivityEntry } from "./electronApi";

export type W1ExecutionEvent =
  | {
      id: string;
      kind: "activity";
      timestamp: string;
      activity: W1ActivityEntry;
    }
  | { id: string; kind: "chunk"; timestamp: string; chunk: ChunkLogEntry };

const timestampValue = (timestamp: string) => {
  const value = Date.parse(timestamp);
  return Number.isNaN(value) ? null : value;
};

/**
 * Presents sidecar's independently polled activity and chunk feeds as one
 * stable, chronological timeline without changing the underlying store shape.
 */
export const createW1ExecutionStream = (
  activities: readonly W1ActivityEntry[],
  chunks: readonly ChunkLogEntry[],
): W1ExecutionEvent[] =>
  [
    ...activities.map((activity, index) => ({
      id: `activity-${activity.id}-${activity.timestamp}-${index}`,
      kind: "activity" as const,
      timestamp: activity.timestamp,
      activity,
      order: index,
    })),
    ...chunks.map((chunk, index) => ({
      id: `chunk-${chunk.chunk_id}-${chunk.timestamp}-${index}`,
      kind: "chunk" as const,
      timestamp: chunk.timestamp,
      chunk,
      order: activities.length + index,
    })),
  ]
    .sort((left, right) => {
      const leftTimestamp = timestampValue(left.timestamp);
      const rightTimestamp = timestampValue(right.timestamp);
      if (leftTimestamp !== null && rightTimestamp !== null)
        return leftTimestamp - rightTimestamp || left.order - right.order;
      if (leftTimestamp !== null) return -1;
      if (rightTimestamp !== null) return 1;
      return left.order - right.order;
    })
    .map(({ order: _order, ...event }) => event);

export const latestW1ExecutionEvent = (stream: readonly W1ExecutionEvent[]) =>
  stream[stream.length - 1];
