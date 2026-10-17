"use client";

import Link from "next/link";
import {
  Check,
  ChevronDown,
  CircleAlert,
  CircleHelp,
  Database,
  Filter,
  Search,
  X,
} from "lucide-react";
import { Popover } from "@base-ui/react/popover";
import { Select as BaseSelect } from "@base-ui/react/select";
import { Badge } from "@/components/ui/badge";
import { classMeta as classes, classOf } from "@/lib/classes";
import { number } from "@/lib/format";
import type { ApiState } from "@/lib/api/use-api";
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
  const item = classOf(id);
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
          ? `No records match ${active.join(" · ")}.`
          : "No records match these filters."}
      </p>
      <button className="text-link" onClick={reset}>
        Clear filters
      </button>
    </div>
  );
}
/** R4: the data cannot answer here. Say so where the answer would be. */
export function Gap({ children }: { children: ReactNode }) {
  return (
    <span className="gap-note">
      <Label type="Unknown" />
      {children}
    </span>
  );
}
/** Placeholder while a request runs. Keep the size close to the real content. */
export function LoadingState({
  label = "Loading data",
  rows = 3,
}: {
  label?: string;
  rows?: number;
}) {
  return (
    <div className="state-loading" role="status" aria-busy="true">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <i key={i} className="skeleton" />
      ))}
    </div>
  );
}
/** A failed request: the API code and message, and a retry button. */
export function ErrorState({
  error,
  retry,
  title = "Could not load this data",
}: {
  error: { code: string; message: string; status?: number };
  retry?: () => void;
  title?: string;
}) {
  return (
    <div className="error-notice state-error" role="alert">
      <CircleAlert size={15} />
      <div>
        <strong>{title}</strong>
        <p>
          {error.message} <code>{error.code}</code>
          {error.status ? <> · HTTP {error.status}</> : null}
        </p>
        {retry && (
          <button className="text-link" onClick={retry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
/** The request worked and returned no data. Say what is missing and why. */
export function NoData({
  title = "No data for this view",
  children,
  action,
}: {
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state" role="status">
      <Database size={24} />
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
/**
 * Shows loading, error or the data. On a reload the old data stays visible.
 * Pass a `skeleton` that looks like the screen to avoid layout jumps.
 */
export function ApiGate<T>({
  state,
  skeleton,
  children,
}: {
  state: ApiState<T>;
  skeleton?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (state.error)
    return <ErrorState error={state.error} retry={state.reload} />;
  if (state.data === null) return <>{skeleton ?? <LoadingState />}</>;
  return <>{children(state.data)}</>;
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
export function NumberLink({
  value,
  href,
}: {
  value: number | string;
  href: string;
}) {
  const text = typeof value === "number" ? number(value) : value;
  // No link when no record is behind the number.
  if (value === 0 || /^0(\.0)?%?$/.test(String(value)))
    return (
      <span className="number-static" title="No records for this value">
        {text}
      </span>
    );
  return (
    <Link className="number-link" href={href}>
      {text}
    </Link>
  );
}
