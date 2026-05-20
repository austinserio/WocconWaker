import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { api, CanonicalRule } from "../api";
import { RuleBadges } from "../components/RuleBadges";
import { RuleEditPanel } from "../components/RuleEditPanel";
import { EmptyState, PageHeader, PillTabs, Spinner } from "../components/ui";
import { Taxonomy } from "../taxonomy";

const NOTE_CATEGORIES = [
  { id: "grammar" as const, label: "Grammar" },
  { id: "pronunciation" as const, label: "Pronunciation" },
  { id: "cultural" as const, label: "Cultural" },
];

interface RuleGroup {
  grammar_domain: string;
  label: string;
  count: number;
  rules: CanonicalRule[];
}

interface Stats {
  total: number;
  by_domain: Record<string, number>;
}

function SortableRuleCard({
  rule,
  taxonomy,
  editing,
  onEdit,
}: {
  rule: CanonicalRule;
  taxonomy: Taxonomy;
  editing: boolean;
  onEdit: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: rule.id,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={`panel-card p-4 mb-2 ${isDragging ? "opacity-90 scale-[1.01] shadow-card-hover z-10" : ""}`}
    >
      <div className="flex gap-3">
        <button
          type="button"
          className="cursor-grab text-render-subtle hover:text-render-text px-1 shrink-0"
          {...attributes}
          {...listeners}
        >
          ⋮⋮
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-render-text leading-relaxed">{rule.content}</p>
          <RuleBadges
            taxonomy={taxonomy}
            grammar_domain={rule.grammar_domain}
            pos_tag={rule.pos_tag}
            construction_type={rule.construction_type}
          />
          <div className="flex gap-3 mt-2">
            {rule.source_url && (
              <a
                href={rule.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-render-muted hover:text-white transition-colors"
              >
                Source →
              </a>
            )}
            <button type="button" onClick={onEdit} className="text-xs text-render-muted hover:text-white">
              {editing ? "Close" : "Edit tags"}
            </button>
          </div>
        </div>
      </div>
    </li>
  );
}

function GrammarRulesView({ taxonomy }: { taxonomy: Taxonomy }) {
  const [groups, setGroups] = useState<RuleGroup[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeDomain, setActiveDomain] = useState<string | null>(null);
  const [posFilter, setPosFilter] = useState<string | null>(null);
  const [constructionFilter, setConstructionFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [editId, setEditId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ category: "grammar" });
    if (posFilter) params.set("pos_tag", posFilter);
    if (constructionFilter) params.set("construction_type", constructionFilter);
    if (search.trim()) params.set("q", search.trim());
    Promise.all([
      api<RuleGroup[]>(`/rules/grouped?${params}`),
      api<Stats>("/rules/stats?category=grammar"),
    ])
      .then(([g, s]) => {
        setGroups(g);
        setStats(s);
        setActiveDomain((prev) => prev ?? g[0]?.grammar_domain ?? null);
      })
      .finally(() => setLoading(false));
  }, [posFilter, constructionFilter, search]);

  useEffect(() => {
    load();
  }, [load]);

  const visibleGroups = useMemo(() => {
    if (activeDomain) return groups.filter((g) => g.grammar_domain === activeDomain);
    return groups;
  }, [groups, activeDomain]);

  const activeGroup = visibleGroups[0];

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const onDragEnd = async (event: DragEndEvent) => {
    if (!activeGroup) return;
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const rules = [...activeGroup.rules];
    const oldIndex = rules.findIndex((r) => r.id === active.id);
    const newIndex = rules.findIndex((r) => r.id === over.id);
    const reordered = arrayMove(rules, oldIndex, newIndex);
    setGroups((prev) =>
      prev.map((g) =>
        g.grammar_domain === activeGroup.grammar_domain ? { ...g, rules: reordered } : g
      )
    );
    await api("/rules/reorder", {
      method: "PATCH",
      body: JSON.stringify({
        category: "grammar",
        grammar_domain: activeGroup.grammar_domain,
        ordered_ids: reordered.map((r) => r.id),
      }),
    });
  };

  const domainNav = taxonomy.grammar_domains.map((d) => ({
    ...d,
    count: stats?.by_domain[d.id] ?? 0,
  }));

  return (
    <div className="flex gap-6">
      <aside className="w-52 shrink-0 space-y-1">
        <p className="text-[10px] uppercase tracking-wider text-render-subtle px-3 mb-2">
          Grammar area
        </p>
        {domainNav.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => setActiveDomain(d.id)}
            className={`w-full text-left rounded-full px-3 py-2 text-sm transition-all duration-200 flex justify-between gap-2 ${
              activeDomain === d.id
                ? "bg-white/10 text-white"
                : "text-render-muted hover:bg-white/5 hover:text-render-text"
            }`}
          >
            <span className="truncate">{d.label}</span>
            <span className="text-xs text-render-subtle shrink-0">{d.count}</span>
          </button>
        ))}
      </aside>

      <div className="flex-1 min-w-0">
        <input
          type="search"
          placeholder="Search rules…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-field mb-4 max-w-md"
        />

        <div className="flex flex-wrap gap-2 mb-4">
          <span className="text-xs text-render-subtle self-center mr-1">POS:</span>
          <button
            type="button"
            onClick={() => setPosFilter(null)}
            className={`pill-tab text-xs py-1 ${!posFilter ? "pill-tab-active" : "pill-tab-inactive"}`}
          >
            All
          </button>
          {taxonomy.pos_tags.slice(0, 8).map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setPosFilter(posFilter === p.id ? null : p.id)}
              className={`pill-tab text-xs py-1 ${
                posFilter === p.id ? "pill-tab-active" : "pill-tab-inactive"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-2 mb-6">
          <span className="text-xs text-render-subtle self-center mr-1">Construction:</span>
          <button
            type="button"
            onClick={() => setConstructionFilter(null)}
            className={`pill-tab text-xs py-1 ${!constructionFilter ? "pill-tab-active" : "pill-tab-inactive"}`}
          >
            All
          </button>
          {taxonomy.construction_types.slice(0, 10).map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setConstructionFilter(constructionFilter === c.id ? null : c.id)}
              className={`pill-tab text-xs py-1 ${
                constructionFilter === c.id ? "pill-tab-active" : "pill-tab-inactive"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-render-muted py-8">
            <Spinner />
            <span className="text-sm">Loading…</span>
          </div>
        ) : !activeGroup || activeGroup.rules.length === 0 ? (
          <EmptyState message="No rules match these filters." />
        ) : (
          <>
            <div className="mb-4">
              <h3 className="text-lg font-medium text-render-text">{activeGroup.label}</h3>
              <p className="text-xs text-render-muted mt-1">
                {taxonomy.grammar_domains.find((d) => d.id === activeGroup.grammar_domain)?.description}
              </p>
            </div>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
              <SortableContext
                items={activeGroup.rules.map((r) => r.id)}
                strategy={verticalListSortingStrategy}
              >
                <ul>
                  {activeGroup.rules.map((r) => (
                    <div key={r.id}>
                      <SortableRuleCard
                        rule={r}
                        taxonomy={taxonomy}
                        editing={editId === r.id}
                        onEdit={() => setEditId(editId === r.id ? null : r.id)}
                      />
                      {editId === r.id && (
                        <RuleEditPanel
                          rule={r}
                          taxonomy={taxonomy}
                          onClose={() => setEditId(null)}
                          onSaved={load}
                        />
                      )}
                    </div>
                  ))}
                </ul>
              </SortableContext>
            </DndContext>
          </>
        )}
      </div>
    </div>
  );
}

function SimpleRulesList({ category }: { category: string }) {
  const [rules, setRules] = useState<CanonicalRule[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<CanonicalRule[]>(`/rules?category=${category}`).then(setRules).finally(() => setLoading(false));
  }, [category]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-render-muted py-8">
        <Spinner />
        <span className="text-sm">Loading…</span>
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {rules.map((r) => (
        <li key={r.id} className="panel-card p-4">
          <p className="text-sm text-render-text">{r.content}</p>
          {r.source_url && (
            <a
              href={r.source_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-render-muted hover:text-white mt-2 inline-block"
            >
              Source →
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function Rules() {
  const [category, setCategory] = useState<(typeof NOTE_CATEGORIES)[number]["id"]>("grammar");
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);

  useEffect(() => {
    api<Taxonomy>("/rules/taxonomy").then(setTaxonomy);
  }, []);

  return (
    <div>
      <PageHeader
        title="Language rules"
        subtitle={
          category === "grammar"
            ? "Organized by grammar area, part of speech, and sentence construction. Edit tags on any rule."
            : "Drag to reorder where supported."
        }
      />

      <div className="mb-6">
        <PillTabs options={NOTE_CATEGORIES} value={category} onChange={setCategory} />
      </div>

      {category === "grammar" && taxonomy ? (
        <GrammarRulesView taxonomy={taxonomy} />
      ) : (
        <SimpleRulesList category={category} />
      )}
    </div>
  );
}
