import { useEffect, useState } from "react";
import { api, LexiconEntry, LexiconListResponse } from "../api";

export function BaseWordPicker({
  onSelect,
  onCancel,
}: {
  onSelect: (entry: LexiconEntry) => void;
  onCancel: () => void;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<LexiconEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true);
      const params = new URLSearchParams({ page_size: "20", sort: "woccon" });
      if (q.trim()) params.set("q", q.trim());
      api<LexiconListResponse>(`/lexicon/base?${params}`)
        .then((r) => setItems(r.items))
        .finally(() => setLoading(false));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [q]);

  return (
    <div className="mt-3 p-3 rounded-xl bg-black/20 border border-render-border space-y-2">
      <input
        className="input-field text-sm"
        placeholder="Search base vocabulary…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoFocus
      />
      {loading && <p className="text-xs text-render-muted">Searching…</p>}
      <ul className="max-h-40 overflow-y-auto space-y-1">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onSelect(item)}
              className="w-full text-left text-sm px-2 py-1 rounded hover:bg-white/5"
            >
              <span className="font-medium text-white">{item.woccon}</span>
              <span className="text-render-muted"> — {item.english}</span>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={onCancel} className="btn-secondary text-xs">
        Cancel
      </button>
    </div>
  );
}
