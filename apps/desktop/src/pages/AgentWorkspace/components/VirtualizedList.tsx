import { useState, useRef, useEffect } from "react";

export function VirtualizedList<T>({
  items,
  rowHeight,
  height,
  renderRow,
  className = "",
}: {
  items: T[];
  rowHeight: number;
  height: number;
  renderRow: (item: T, index: number) => React.ReactNode;
  className?: string;
}) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const totalHeight = items.length * rowHeight;
  const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - 2);
  const endIndex = Math.min(items.length - 1, Math.floor((scrollTop + height) / rowHeight) + 2);

  const visibleItems = items.slice(startIndex, endIndex + 1);
  const offsetY = startIndex * rowHeight;

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  };

  // Scroll to bottom on items change if scroll was near bottom
  useEffect(() => {
    if (containerRef.current) {
      const container = containerRef.current;
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120;
      if (isNearBottom) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }, [items.length]);

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className={className}
      style={{ height, overflowY: "auto", position: "relative" }}
    >
      <div style={{ height: totalHeight, width: "100%", position: "relative" }}>
        <div
          style={{
            transform: `translateY(${offsetY}px)`,
            position: "absolute",
            left: 0,
            right: 0,
            top: 0,
          }}
        >
          {visibleItems.map((item, index) => renderRow(item, startIndex + index))}
        </div>
      </div>
    </div>
  );
}
