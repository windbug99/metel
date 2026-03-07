"use client";

import { useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type DateRangePickerProps = {
  from: string;
  to: string;
  onChange: (next: { from: string; to: string }) => void;
  className?: string;
};

function startOfDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function parseDateValue(value: string): Date | null {
  if (!value) {
    return null;
  }
  const normalized = value.includes("T") ? value.slice(0, 10) : value;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return startOfDay(parsed);
}

function formatDateLabel(value: Date | null) {
  if (!value) {
    return "--";
  }
  return value.toLocaleDateString();
}

function toISODate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addMonths(value: Date, amount: number) {
  return new Date(value.getFullYear(), value.getMonth() + amount, 1);
}

function monthTitle(value: Date) {
  return value.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function isSameDate(a: Date | null, b: Date | null) {
  if (!a || !b) {
    return false;
  }
  return a.getTime() === b.getTime();
}

function isInRange(day: Date, from: Date | null, to: Date | null) {
  if (!from || !to) {
    return false;
  }
  return day > from && day < to;
}

function monthGrid(month: Date) {
  const monthStart = new Date(month.getFullYear(), month.getMonth(), 1);
  const gridStart = addDays(monthStart, -monthStart.getDay());
  return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
}

function addDays(value: Date, amount: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + amount);
  return startOfDay(next);
}

export function DateRangePicker({ from, to, onChange, className }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState(() => {
    const initial = parseDateValue(from);
    const base = initial ?? new Date();
    return new Date(base.getFullYear(), base.getMonth(), 1);
  });
  const rootRef = useRef<HTMLDivElement | null>(null);
  const selectedFrom = parseDateValue(from);
  const selectedTo = parseDateValue(to);

  useEffect(() => {
    if (!selectedFrom) {
      return;
    }
    setViewMonth(new Date(selectedFrom.getFullYear(), selectedFrom.getMonth(), 1));
  }, [selectedFrom?.getTime()]);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current) {
        return;
      }
      if (rootRef.current.contains(event.target as Node)) {
        return;
      }
      setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, []);

  const handleSelect = (day: Date) => {
    if (!selectedFrom || (selectedFrom && selectedTo)) {
      onChange({ from: toISODate(day), to: "" });
      return;
    }
    if (day < selectedFrom) {
      onChange({ from: toISODate(day), to: toISODate(selectedFrom) });
      return;
    }
    onChange({ from: toISODate(selectedFrom), to: toISODate(day) });
  };

  return (
    <div ref={rootRef} className="relative">
      <Button
        type="button"
        variant="outline"
        onClick={() => setOpen((prev) => !prev)}
        className={cn("h-11 min-w-[320px] justify-start gap-2 rounded-md px-3 text-sm md:h-9", className)}
      >
        <CalendarDays className="h-4 w-4" />
        <span className="truncate">
          {formatDateLabel(selectedFrom)} ~ {formatDateLabel(selectedTo)}
        </span>
      </Button>
      {open ? (
        <div className="absolute right-0 top-full z-40 mt-2 w-[560px] max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-popover p-3 shadow-md">
          <div className="mb-3 flex items-center justify-between">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setViewMonth((prev) => addMonths(prev, -1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="grid flex-1 grid-cols-2">
              <p className="text-center text-sm font-medium">{monthTitle(viewMonth)}</p>
              <p className="text-center text-sm font-medium">{monthTitle(addMonths(viewMonth, 1))}</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setViewMonth((prev) => addMonths(prev, 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[viewMonth, addMonths(viewMonth, 1)].map((month) => (
              <div key={`${month.getFullYear()}-${month.getMonth()}`}>
                <div className="mb-1 grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
                  {["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map((label) => (
                    <span key={label}>{label}</span>
                  ))}
                </div>
                <div className="grid grid-cols-7 gap-1">
                  {monthGrid(month).map((day) => {
                    const inMonth = day.getMonth() === month.getMonth();
                    const isFrom = isSameDate(day, selectedFrom);
                    const isTo = isSameDate(day, selectedTo);
                    const inRange = isInRange(day, selectedFrom, selectedTo);
                    return (
                      <button
                        key={day.toISOString()}
                        type="button"
                        onClick={() => handleSelect(day)}
                        className={cn(
                          "h-8 w-8 rounded-md text-sm transition-colors",
                          "hover:bg-muted",
                          !inMonth && "text-muted-foreground/50",
                          inRange && "rounded-none bg-muted",
                          (isFrom || isTo) && "bg-primary text-primary-foreground hover:bg-primary/90"
                        )}
                      >
                        {day.getDate()}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
