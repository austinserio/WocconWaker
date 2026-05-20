import { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4 animate-slide-up">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({
  children,
  className = "",
  hover = true,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div className={`${hover ? "panel-card" : "panel-card"} ${className} animate-fade-in`}>
      {children}
    </div>
  );
}

export function PillTabs<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex gap-1 rounded-full border border-render-border bg-render-surface p-1">
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id)}
          className={`pill-tab ${
            value === opt.id ? "pill-tab-active" : "pill-tab-inactive"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function Spinner() {
  return (
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-white" />
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <p className="py-12 text-center text-sm text-render-muted animate-pulse-soft">{message}</p>
  );
}
