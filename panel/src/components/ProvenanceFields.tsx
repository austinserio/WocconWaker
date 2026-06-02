export interface ProvenanceValues {
  source_page: string;
  source_page_end: string;
  source_excerpt: string;
}

export function provenanceFromRow(row?: {
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  citation?: { page?: number | null; page_end?: number | null; excerpt?: string | null } | null;
}): ProvenanceValues {
  const page = row?.source_page ?? row?.citation?.page;
  const pageEnd = row?.source_page_end ?? row?.citation?.page_end;
  const excerpt = row?.source_excerpt ?? row?.citation?.excerpt;
  return {
    source_page: page != null ? String(page) : "",
    source_page_end: pageEnd != null ? String(pageEnd) : "",
    source_excerpt: excerpt ?? "",
  };
}

export function provenancePayload(values: ProvenanceValues) {
  const page = values.source_page.trim() ? parseInt(values.source_page, 10) : null;
  const pageEnd = values.source_page_end.trim() ? parseInt(values.source_page_end, 10) : null;
  const excerpt = values.source_excerpt.trim() || null;
  return {
    source_page: Number.isFinite(page) ? page : null,
    source_page_end: Number.isFinite(pageEnd) ? pageEnd : null,
    source_excerpt: excerpt,
  };
}

export function ProvenanceFields({
  values,
  onChange,
}: {
  values: ProvenanceValues;
  onChange: (values: ProvenanceValues) => void;
}) {
  const set = (key: keyof ProvenanceValues, value: string) =>
    onChange({ ...values, [key]: value });

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <label className="block">
        <span className="text-[10px] uppercase tracking-wide text-render-subtle">Source page</span>
        <input
          type="number"
          min={1}
          value={values.source_page}
          onChange={(e) => set("source_page", e.target.value)}
          className="input-field mt-1 text-xs"
          placeholder="e.g. 42"
        />
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-wide text-render-subtle">Page end</span>
        <input
          type="number"
          min={1}
          value={values.source_page_end}
          onChange={(e) => set("source_page_end", e.target.value)}
          className="input-field mt-1 text-xs"
          placeholder="optional"
        />
      </label>
      <label className="block sm:col-span-1">
        <span className="text-[10px] uppercase tracking-wide text-render-subtle">Excerpt</span>
        <textarea
          value={values.source_excerpt}
          onChange={(e) => set("source_excerpt", e.target.value)}
          rows={2}
          className="input-field mt-1 text-xs resize-y min-h-[2.5rem]"
          placeholder="Surrounding text for verification"
        />
      </label>
    </div>
  );
}
