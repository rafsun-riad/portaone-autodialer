"use client";

import * as React from "react";
import { Legend as RechartsLegend, Tooltip as RechartsTooltip } from "recharts";

import { cn } from "@/lib/utils";

export type ChartConfig = Record<
  string,
  {
    label?: React.ReactNode;
    color?: string;
  }
>;

type ChartContextValue = {
  config: ChartConfig;
};

const ChartContext = React.createContext<ChartContextValue | null>(null);

function useChart() {
  const context = React.useContext(ChartContext);
  if (!context) {
    throw new Error("Chart components must be used within a ChartContainer.");
  }
  return context;
}

const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & {
    config: ChartConfig;
  }
>(({ className, config, style, children, ...props }, ref) => {
  const chartStyle = Object.entries(config).reduce(
    (accumulator, [key, value]) => {
      if (value.color) {
        accumulator[`--color-${key}`] = value.color;
      }
      return accumulator;
    },
    {} as Record<string, string>,
  );

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        ref={ref}
        className={cn(
          "w-full [&_.recharts-cartesian-axis-tick_text]:fill-slate-500 [&_.recharts-cartesian-grid_line]:stroke-slate-200 [&_.recharts-curve.recharts-tooltip-cursor]:stroke-slate-300 [&_.recharts-default-tooltip]:rounded-2xl [&_.recharts-default-tooltip]:border-none [&_.recharts-layer]:outline-none [&_.recharts-pie-label-text]:fill-slate-700 [&_.recharts-polar-grid_[stroke='#ccc']]:stroke-slate-200",
          className,
        )}
        style={{ ...chartStyle, ...style } as React.CSSProperties}
        {...props}
      >
        {children}
      </div>
    </ChartContext.Provider>
  );
});
ChartContainer.displayName = "ChartContainer";

const ChartTooltip = RechartsTooltip;

function ChartTooltipContent({
  active,
  payload,
  label,
  className,
  indicator = "dot",
  hideLabel = false,
  hideIndicator = false,
  labelFormatter,
  nameKey,
}: {
  active?: boolean;
  payload?: Array<{
    color?: string;
    dataKey?: string;
    name?: string;
    value?: number | string;
    payload?: Record<string, unknown>;
  }>;
  label?: string | number;
  className?: string;
  indicator?: "dot" | "line";
  hideLabel?: boolean;
  hideIndicator?: boolean;
  labelFormatter?: (value: string | number) => React.ReactNode;
  nameKey?: string;
}) {
  const { config } = useChart();

  if (!active || !payload?.length) {
    return null;
  }

  const formattedLabel = hideLabel
    ? null
    : labelFormatter
      ? labelFormatter(label ?? "")
      : label;

  return (
    <div
      className={cn(
        "min-w-48 rounded-2xl border border-slate-200 bg-white/96 px-3 py-2 text-xs shadow-[0_20px_35px_rgba(15,23,42,0.08)]",
        className,
      )}
    >
      {formattedLabel ? (
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
          {formattedLabel}
        </div>
      ) : null}
      <div className="space-y-1.5">
        {payload.map((item) => {
          const itemKey = String(
            (nameKey && item.payload?.[nameKey]) ??
              item.dataKey ??
              item.name ??
              "",
          );
          const itemConfig = config[itemKey];

          return (
            <div
              key={`${itemKey}-${item.value ?? ""}`}
              className="flex items-center justify-between gap-3"
            >
              <div className="flex items-center gap-2 text-slate-600">
                {!hideIndicator ? (
                  <span
                    className={cn(
                      "block shrink-0 rounded-full",
                      indicator === "line"
                        ? "h-0.5 w-3 rounded-sm"
                        : "size-2.5",
                    )}
                    style={{
                      backgroundColor:
                        item.color ?? itemConfig?.color ?? "#94a3b8",
                    }}
                  />
                ) : null}
                <span>{itemConfig?.label ?? item.name ?? itemKey}</span>
              </div>
              <span className="font-semibold tabular-nums text-slate-950">
                {typeof item.value === "number"
                  ? item.value.toLocaleString()
                  : item.value}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ChartLegend = RechartsLegend;

function ChartLegendContent({
  payload,
  className,
}: {
  payload?: Array<{
    color?: string;
    dataKey?: string;
    value?: string;
  }>;
  className?: string;
}) {
  const { config } = useChart();

  if (!payload?.length) {
    return null;
  }

  return (
    <div className={cn("mt-4 flex flex-wrap items-center gap-3", className)}>
      {payload.map((item) => {
        const itemKey = String(item.dataKey ?? item.value ?? "");
        const itemConfig = config[itemKey];

        return (
          <div
            key={itemKey}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600"
          >
            <span
              className="size-2.5 rounded-full"
              style={{
                backgroundColor: item.color ?? itemConfig?.color ?? "#94a3b8",
              }}
            />
            <span>{itemConfig?.label ?? item.value ?? itemKey}</span>
          </div>
        );
      })}
    </div>
  );
}

export {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
};
