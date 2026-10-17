"use client";

import Link from "next/link";
import {
  Check,
  ChevronDown,
  CircleHelp,
  Filter,
  Search,
  X,
} from "lucide-react";
import { Popover } from "@base-ui/react/popover";
import { Select as BaseSelect } from "@base-ui/react/select";
import { Badge } from "@/components/ui/badge";
import {
  binTotal,
  classes,
  number,
  rangeOf,
  sampleCount,
} from "@/lib/mock-data";
import type { KeyboardEvent, ReactNode } from "react";

export type Href = (path: string, filters?: Record<string, string>) => string;
export type OpenDetail = (type: string, id: string) => void;
export function Label({ type = "Observed" }: { type?: string }) {
  return (
    <span className={`evidence-label ${type.toLowerCase()}`}>
      <span />
      {type}
    </span>
  );
}
export function Tip({
  text,
  children,
}: {
  text: string;
  children?: ReactNode;
}) {
  // A click popover, so touch and keyboard users can read the help too.
  return (
    <Popover.Root>
      <Popover.Trigger
        className="help-icon"
        aria-label={`Help: ${text}`}
        openOnHover
        delay={150}
      >
        {children || <CircleHelp size={13} />}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="top" sideOffset={6} className="z-50">
          <Popover.Popup className="help-popup">{text}</Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
export function Status({ value }: { value: string }) {
  const tone = ["VERIFIED", "Complete", "Healthy", "High"].includes(value)
    ? "green"
    : ["SPOOFED", "Failed"].includes(value)
      ? "red"
      : ["CLAIMED", "UNVERIFIED", "Medium", "In progress"].includes(value)
        ? "amber"
        : value === "New"
          ? "purple"
          : "neutral";
  return (
    <Badge variant="outline" className={`status ${tone}`}>
      <span className="status-dot" />
      {value}
    </Badge>
  );
}
export function ClassName({
  id,
  full = false,
}: {
  id: number;
  full?: boolean;
}) {
  const item = classes.find((c) => c.id === id)!;
  return (
    <span className="class-name">
      <i style={{ background: item.color }} />
      {full ? item.name : item.short}
    </span>
  );
}
export function Panel({
  title,
  children,
  action,
  label,
  className = "",
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  label?: string;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <h2>{title}</h2>
        {label && <Label type={label} />}
        <div className="panel-action">{action}</div>
      </div>
      {children}
    </section>
  );
}
export function TextLink({
  children,
  onClick,
  className = "",
}: {
  children: ReactNode;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button className={`text-link ${className}`} onClick={onClick}>
      {children}
    </button>
  );
}
export function Select({
  label,
  value,
  onChange,
  options,
  icon,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  icon?: ReactNode;
}) {
  // An unknown URL value shows the first option, which is the default.
  const current = options.find((o) => o.value === value) || options[0];
  return (
    <BaseSelect.Root
      modal={false}
      value={current.value}
      onValueChange={(v) => v !== null && v !== current.value && onChange(v)}
    >
      <BaseSelect.Trigger className="select-control" aria-label={label}>
        {icon}
        <BaseSelect.Value className="select-value">
          {() => current.label}
        </BaseSelect.Value>
        <BaseSelect.Icon className="select-chevron">
          <ChevronDown size={12} />
        </BaseSelect.Icon>
      </BaseSelect.Trigger>
      <SelectPopup>
        {options.map((option) => (
          <BaseSelect.Item
            key={option.value}
            value={option.value}
            className="select-item"
          >
            <BaseSelect.ItemIndicator className="select-check">
              <Check size={12} />
            </BaseSelect.ItemIndicator>
            <BaseSelect.ItemText>{option.label}</BaseSelect.ItemText>
          </BaseSelect.Item>
        ))}
      </SelectPopup>
    </BaseSelect.Root>
  );
}
export function ClassFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  // An empty value means all classes. Unknown ids from the URL are ignored.
  const ids = value.split(",");
  const selected = classes
    .filter((c) => ids.includes(String(c.id)))
    .map((c) => String(c.id));
  function change(next: string[]) {
    const ordered = classes
      .map((c) => String(c.id))
      .filter((id) => next.includes(id));
    onChange(ordered.length === classes.length ? "" : ordered.join(","));
  }
  return (
    <BaseSelect.Root
      multiple
      modal={false}
      value={selected}
      onValueChange={change}
    >
      <BaseSelect.Trigger
        className="select-control class-filter"
        aria-label="Traffic classes"
      >
        <Filter size={13} />
        <BaseSelect.Value className="select-value">
          {() =>
            selected.length === 1 ? (
              classes.find((c) => String(c.id) === selected[0])!.short
            ) : selected.length ? (
              `${selected.length} classes`
            ) : (
              <>
                <span className="desktop-only">All traffic classes</span>
                <span className="mobile-only">All classes</span>
              </>
            )
          }
        </BaseSelect.Value>
        <BaseSelect.Icon className="select-chevron">
          <ChevronDown size={12} />
        </BaseSelect.Icon>
      </BaseSelect.Trigger>
      <SelectPopup
        className="class-popover"
        header={
          <div className="popover-heading">
            Traffic classes
            <button disabled={!selected.length} onClick={() => onChange("")}>
              Reset
            </button>
          </div>
        }
        footer={<p>No selection includes all classes.</p>}
      >
        {classes.map((c) => (
          <BaseSelect.Item
            key={c.id}
            value={String(c.id)}
            className="select-item"
          >
            <span className="select-box">
              <BaseSelect.ItemIndicator>
                <Check size={11} />
              </BaseSelect.ItemIndicator>
            </span>
            <BaseSelect.ItemText>
              <ClassName id={c.id} full />
            </BaseSelect.ItemText>
          </BaseSelect.Item>
        ))}
      </SelectPopup>
    </BaseSelect.Root>
  );
}
function SelectPopup({
  children,
  className = "",
  header,
  footer,
}: {
  children: ReactNode;
  className?: string;
  header?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <BaseSelect.Portal>
      <BaseSelect.Positioner
        className="select-positioner"
        side="bottom"
        align="start"
        sideOffset={4}
        alignItemWithTrigger={false}
      >
        <BaseSelect.Popup className={`select-popup ${className}`}>
          {header}
          <BaseSelect.List className="select-list">{children}</BaseSelect.List>
          {footer}
        </BaseSelect.Popup>
      </BaseSelect.Positioner>
    </BaseSelect.Portal>
  );
}
export function Segmented({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string; count?: number }[];
}) {
  // One choice at a time, so it is a radio group: arrow keys move the choice.
  function key(event: KeyboardEvent<HTMLDivElement>) {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[
      event.key
    ];
    if (!step) return;
    event.preventDefault();
    const at = options.findIndex((o) => o.value === value);
    const next = (at + step + options.length) % options.length;
    onChange(options[next].value);
    event.currentTarget
      .querySelectorAll<HTMLButtonElement>("button")
      [next]?.focus();
  }
  return (
    <div
      className="segmented"
      role="radiogroup"
      aria-label={label}
      onKeyDown={key}
    >
      {options.map((o) => {
        const checked = o.value === value;
        return (
          <button
            key={o.value}
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            className={o.count === 0 ? "empty" : ""}
            onClick={() => onChange(o.value)}
          >
            {o.label}
            {o.count !== undefined && <span>{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
export function SearchField({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div className="search-field">
      <Search size={14} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button aria-label="Clear search" onClick={() => onChange("")}>
          <X size={13} />
        </button>
      )}
    </div>
  );
}
export function Empty({
  reset,
  active = [],
}: {
  reset: () => void;
  active?: string[];
}) {
  return (
    <div className="empty-state" role="status">
      <Search size={24} />
      <h3>No matching records</h3>
      <p>
        {active.length
          ? `No sample record matches ${active.join(" · ")}.`
          : "These filters do not match the sample data."}
      </p>
      <button className="text-link" onClick={reset}>
        Clear filters
      </button>
    </div>
  );
}
export function TableFooter({
  count,
  total,
  noun = "records",
}: {
  count: number;
  total?: string;
  noun?: string;
}) {
  return (
    <div className="table-footer">
      <span>
        Showing {count} {noun}
        {total && <> · {total} in this window</>}
      </span>
    </div>
  );
}
const allBins = Array.from({ length: 96 }, (_, i) => binTotal(i)).reduce(
  (a, b) => a + b,
  0,
);
export function TrafficChart({
  href,
  compact = false,
  selected = "",
  range = "24h",
}: {
  href: Href;
  compact?: boolean;
  selected?: string;
  range?: string;
}) {
  const shown = rangeOf(range).bins;
  const height = compact ? 110 : 184;
  const baseline = height - 22;
  const visible = classes.filter(
    (c) => !selected || selected.split(",").includes(String(c.id)),
  );
  return (
    <div className={`traffic-chart ${compact ? "compact-chart" : ""}`}>
      {[false, true].map((mobile) => {
        const width = mobile ? 340 : 900;
        // Hourly bars on phones once the range has more than 24 bins.
        const group = mobile && shown > 24 ? 4 : 1;
        const bins = shown / group;
        const first = 96 - shown;
        const step = (width - 49) / bins;
        const at = (bin: number) => {
          const minutes = 14 * 60 + 5 + bin * 15;
          return `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
        };
        // Requests per bar, from the same class counts as the tables.
        const value = (index: number, share: number) =>
          Array.from({ length: group }, (_, k) => binTotal(index + k)).reduce(
            (a, b) => a + b,
            0,
          ) *
          (share / allBins);
        const stacks = Array.from({ length: bins }, (_, i) =>
          visible.reduce((t, c) => t + value(first + i * group, c.count), 0),
        );
        const raw = Math.max(...stacks, 1);
        // Three gridline steps of 1, 2, 2.5 or 5 × 10^n.
        const unit = 10 ** Math.floor(Math.log10(raw / 3));
        const tick =
          [1, 2, 2.5, 5, 10].map((m) => m * unit).find((t) => t * 3 >= raw) ||
          unit * 10;
        const top = tick * 3;
        const label = (n: number) =>
          n >= 1000 ? `${+(n / 1000).toFixed(1)}k` : String(Math.round(n));
        const tickCount = Math.min(mobile ? 3 : 6, bins);
        const ticks = Array.from({ length: tickCount + 1 }, (_, i) =>
          at(first + Math.round((i * shown) / tickCount)),
        );
        return (
          <svg
            key={String(mobile)}
            className={mobile ? "mobile-chart" : "desktop-chart"}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            focusable="false"
            aria-label={`Sample requests over time, grouped by traffic class${mobile ? ", hourly view" : ""}`}
          >
            {[0, 1, 2, 3].map((i) => {
              const y = 10 + (i * (baseline - 10)) / 3;
              return (
                <g key={i}>
                  <line
                    x1="40"
                    x2={width - 6}
                    y1={y}
                    y2={y}
                    stroke="#323239"
                    strokeDasharray="2 4"
                  />
                  <text
                    x="31"
                    y={y + 4}
                    textAnchor="end"
                    fill="#a6a6b4"
                    fontSize={mobile ? 12 : 10}
                  >
                    {label((top * (3 - i)) / 3)}
                  </text>
                </g>
              );
            })}
            {Array.from({ length: bins }, (_, i) => {
              const index = first + i * group;
              const bucket = at(index);
              let bottom = baseline;
              return (
                <g key={i}>
                  {visible.map((c) => {
                    const n = value(index, c.count);
                    const h = (n / top) * (baseline - 10);
                    bottom -= h;
                    return (
                      <rect
                        key={c.id}
                        x={43 + i * step + (step * 0.7 - Math.min(step * 0.7, 32)) / 2}
                        y={bottom}
                        width={Math.min(step * 0.7, 32)}
                        height={h}
                        fill={c.color}
                        opacity=".9"
                      >
                        <title>{`${c.name} · ${bucket} · ${number(Math.round(n))} requests`}</title>
                      </rect>
                    );
                  })}
                </g>
              );
            })}
            {ticks.map((tick, i) => (
              <text
                key={i}
                x={43 + (i * (width - 49)) / (ticks.length - 1)}
                y={height - 4}
                fill="#a6a6b4"
                fontSize={mobile ? 12 : 10}
                textAnchor={i === ticks.length - 1 ? "end" : "start"}
              >
                {tick}
              </text>
            ))}
          </svg>
        );
      })}
      {!compact && (
        <div className="chart-legend">
          {visible.map((c) => (
            <Link key={c.id} href={href("/events", { class: String(c.id) })}>
              <i style={{ background: c.color }} />
              {c.short}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function Confidence({
  value,
  onClick,
}: {
  value: string;
  onClick?: () => void;
}) {
  const Tag = onClick ? "button" : "span";
  return (
    <Tag
      className={`confidence ${value.toLowerCase()}`}
      onClick={onClick}
      title={
        onClick
          ? `${value} confidence. Open the supporting evidence.`
          : `${value} confidence`
      }
    >
      <span className="confidence-bars">
        <i />
        <i />
        <i />
      </span>
      {value}
    </Tag>
  );
}
/** A link to evidence lists that renders as plain content when the sample is empty. */
export function CountLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  if (!sampleCount(href))
    return (
      <div className="count-static" title="No sample records for this value">
        {children}
      </div>
    );
  return <Link href={href}>{children}</Link>;
}
export function NumberLink({
  value,
  href,
}: {
  value: number | string;
  href: string;
}) {
  const text = typeof value === "number" ? number(value) : value;
  // No link when the sample has no rows behind the number.
  if (value === 0 || /^0(\.0)?%?$/.test(String(value)) || !sampleCount(href))
    return (
      <span className="number-static" title="No sample records for this value">
        {text}
      </span>
    );
  return (
    <Link className="number-link" href={href}>
      {text}
    </Link>
  );
}
