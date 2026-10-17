// shadcn/ui Chart (https://ui.shadcn.com/docs/components/chart), copied into the project:
// a Recharts wrapper that maps a config of series to CSS colour variables, plus a tooltip.
// Trimmed to what Kopi & Keys uses (no legend component).
import * as React from "react";
import * as RechartsPrimitive from "recharts";
import { cn } from "../../lib/utils";

export type ChartConfig = Record<string, { label?: React.ReactNode; color?: string }>;

const ChartContext = React.createContext<{ config: ChartConfig } | null>(null);

function useChart() {
  const context = React.useContext(ChartContext);
  if (!context) throw new Error("useChart must be used within a <ChartContainer />");
  return context;
}

function ChartContainer({
  id,
  className,
  children,
  config,
  ...props
}: React.ComponentProps<"div"> & {
  config: ChartConfig;
  children: React.ComponentProps<typeof RechartsPrimitive.ResponsiveContainer>["children"];
}) {
  const uniqueId = React.useId();
  const chartId = `chart-${id || uniqueId.replace(/:/g, "")}`;
  const colours = Object.entries(config)
    .filter(([, item]) => item.color)
    .map(([key, item]) => `--color-${key}: ${item.color};`)
    .join(" ");
  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        className={cn(
          "flex aspect-video justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-slate-500 [&_.recharts-cartesian-grid_line]:stroke-slate-200 dark:[&_.recharts-cartesian-grid_line]:stroke-slate-700 [&_.recharts-rectangle.recharts-tooltip-cursor]:fill-slate-100 dark:[&_.recharts-rectangle.recharts-tooltip-cursor]:fill-slate-800 [&_.recharts-surface]:outline-none",
          className,
        )}
        {...props}
      >
        <style>{`[data-chart=${chartId}] { ${colours} }`}</style>
        <RechartsPrimitive.ResponsiveContainer>{children}</RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  );
}

const ChartTooltip = RechartsPrimitive.Tooltip;

type TooltipPayloadItem = { dataKey?: string | number; name?: string; value?: number | string; color?: string };

function ChartTooltipContent({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: React.ReactNode;
  formatter?: (value: number | string) => React.ReactNode;
}) {
  const { config } = useChart();
  if (!active || !payload?.length) return null;
  return (
    <div className="grid min-w-[8rem] gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-md dark:border-slate-700 dark:bg-slate-900">
      {label && <div className="font-medium">{label}</div>}
      {payload.map((item) => {
        const key = String(item.dataKey ?? item.name ?? "value");
        return (
          <div key={key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-slate-500">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: item.color ?? `var(--color-${key})` }} />
              {config[key]?.label ?? key}
            </span>
            <span className="font-mono font-medium tabular-nums">
              {formatter && item.value !== undefined ? formatter(item.value) : item.value}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export { ChartContainer, ChartTooltip, ChartTooltipContent };
