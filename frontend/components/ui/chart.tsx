"use client"

import * as React from "react"
import * as RechartsPrimitive from "recharts"

import { cn } from "@/lib/utils"

export type ChartConfig = {
  [k in string]: {
    label?: React.ReactNode
    color?: string
  }
}

const ChartContext = React.createContext<{ config: ChartConfig } | null>(null)

function useChart() {
  const context = React.useContext(ChartContext)
  if (!context) {
    throw new Error("useChart must be used within a <ChartContainer />")
  }
  return context
}

type ChartContainerProps = React.ComponentProps<"div"> & {
  config: ChartConfig
  children: React.ComponentProps<typeof RechartsPrimitive.ResponsiveContainer>["children"]
}

export function ChartContainer({ id, className, children, config, ...props }: ChartContainerProps) {
  const uniqueId = React.useId()
  const chartId = `chart-${id || uniqueId.replace(/:/g, "")}`

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        className={cn(
          "flex aspect-video justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line]:stroke-border/50 [&_.recharts-layer[tabindex]]:outline-none [&_.recharts-legend-item-text]:text-foreground [&_.recharts-polar-grid_[stroke='#ccc']]:stroke-border [&_.recharts-radial-bar-background-sector]:fill-muted [&_.recharts-reference-line_[stroke='#ccc']]:stroke-border [&_.recharts-sector[stroke='#fff']]:stroke-transparent [&_.recharts-tooltip-cursor]:stroke-border [&_.recharts-tooltip-cursor]:fill-transparent [&_.recharts-surface]:outline-none",
          className
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        <RechartsPrimitive.ResponsiveContainer>{children}</RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
}

const ChartStyle = ({ id, config }: { id: string; config: ChartConfig }) => {
  const colorConfig = Object.entries(config).filter(([, value]) => Boolean(value.color))

  if (!colorConfig.length) {
    return null
  }

  return (
    <style
      dangerouslySetInnerHTML={{
        __html: `
[data-chart=${id}] {
${colorConfig
  .map(([key, value]) => {
    return `  --color-${key}: ${value.color};`
  })
  .join("\n")}
}
`,
      }}
    />
  )
}

const ChartTooltip = RechartsPrimitive.Tooltip

type ChartTooltipContentProps = React.ComponentProps<typeof RechartsPrimitive.Tooltip> &
  React.ComponentProps<"div"> & {
    hideLabel?: boolean
    hideIndicator?: boolean
    indicator?: "line" | "dot"
  }

function ChartTooltipContent({
  active,
  payload,
  className,
  hideLabel = false,
  hideIndicator = false,
  label,
  labelFormatter,
  formatter,
  color,
  indicator = "dot",
}: ChartTooltipContentProps) {
  const { config } = useChart()

  if (!active || !payload?.length) {
    return null
  }

  const tooltipLabel = !hideLabel
    ? labelFormatter
      ? labelFormatter(label, payload)
      : label
    : null

  return (
    <div className={cn("grid min-w-[8rem] gap-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs shadow-xl", className)}>
      {tooltipLabel ? <div className="font-medium text-foreground">{tooltipLabel}</div> : null}
      <div className="grid gap-1">
        {payload.map((item: unknown, index: number) => {
          const entry = item as {
            dataKey?: string | number
            name?: string | number
            color?: string
            payload?: { fill?: string }
            value?: number | string
          }
          const key = String(entry.dataKey ?? entry.name ?? `item-${index}`)
          const itemConfig = config[key] ?? config[String(entry.name)] ?? undefined
          const itemColor = color || entry.color || entry.payload?.fill

          return (
            <div key={key} className="flex items-center gap-2 text-muted-foreground">
              {hideIndicator ? null : (
                <span
                  className={cn("shrink-0 rounded-[2px]", indicator === "dot" ? "h-2 w-2 rounded-full" : "h-2 w-4")}
                  style={{ backgroundColor: itemColor }}
                />
              )}
              <span className="grow">{itemConfig?.label ?? entry.name}</span>
              <span className="font-mono font-medium text-foreground">
                {formatter
                  ? formatter(entry.value ?? 0, entry.name ?? key, entry, index, payload)
                  : entry.value?.toLocaleString()}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export { ChartTooltip, ChartTooltipContent }
