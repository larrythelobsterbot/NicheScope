"use client";

interface SkeletonProps {
  type?: "chart" | "table" | "radar" | "map" | "list";
  height?: string;
}

export default function Skeleton({ type = "chart", height = "100%" }: SkeletonProps) {
  if (type === "chart") {
    return (
      <div className="w-full h-full flex flex-col justify-end gap-1 p-4 animate-pulse" style={{ height }}>
        <div className="flex items-end gap-2 flex-1">
          {Array.from({ length: 12 }, (_, i) => (
            <div
              key={i}
              className="flex-1 bg-white/5 rounded-t"
              style={{ height: `${20 + Math.random() * 60}%` }}
            />
          ))}
        </div>
        <div className="h-px bg-white/5 mt-2" />
        <div className="flex justify-between mt-1">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-2 w-8 bg-white/5 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (type === "radar") {
    return (
      <div className="w-full h-full flex items-center justify-center animate-pulse" style={{ height }}>
        <div className="relative">
          {[100, 75, 50, 25].map((size) => (
            <div
              key={size}
              className="absolute border border-white/5 rounded-full"
              style={{
                width: size * 2.5,
                height: size * 2.5,
                top: `${(100 - size) * 1.25}px`,
                left: `${(100 - size) * 1.25}px`,
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  if (type === "map") {
    return (
      <div className="w-full h-full flex items-center justify-center animate-pulse" style={{ height }}>
        <div className="text-slate-600 text-sm">Loading map data...</div>
      </div>
    );
  }

  if (type === "table") {
    return (
      <div className="w-full h-full space-y-3 p-4 animate-pulse" style={{ height }}>
        <div className="h-3 bg-white/5 rounded w-full" />
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="flex gap-4">
            <div className="h-3 bg-white/5 rounded flex-1" />
            <div className="h-3 bg-white/5 rounded w-20" />
            <div className="h-3 bg-white/5 rounded w-16" />
          </div>
        ))}
      </div>
    );
  }

  // list type
  return (
    <div className="w-full space-y-2 animate-pulse" style={{ height }}>
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex items-center gap-3 py-2 px-3">
          <div className="w-5 h-3 bg-white/5 rounded" />
          <div className="w-2 h-2 bg-white/5 rounded-full" />
          <div className="h-3 bg-white/5 rounded flex-1" />
          <div className="h-3 bg-white/5 rounded w-10" />
          <div className="h-5 bg-white/5 rounded-full w-14" />
        </div>
      ))}
    </div>
  );
}
