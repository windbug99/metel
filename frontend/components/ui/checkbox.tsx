import * as React from "react"

import { cn } from "@/lib/utils"

export type CheckboxProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "onChange"> & {
  onCheckedChange?: (checked: boolean) => void
}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, onCheckedChange, ...props }, ref) => {
    return (
      <input
        type="checkbox"
        ref={ref}
        className={cn(
          "peer h-4 w-4 shrink-0 rounded-sm border border-border bg-background text-primary accent-primary shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 checked:border-primary checked:bg-primary",
          className
        )}
        onChange={(event) => onCheckedChange?.(event.target.checked)}
        {...props}
      />
    )
  }
)
Checkbox.displayName = "Checkbox"

export { Checkbox }
