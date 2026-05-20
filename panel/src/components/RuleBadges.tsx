import { labelFor, Taxonomy } from "../taxonomy";

export function RuleBadges({
  taxonomy,
  grammar_domain,
  pos_tag,
  construction_type,
}: {
  taxonomy: Taxonomy;
  grammar_domain?: string | null;
  pos_tag?: string | null;
  construction_type?: string | null;
}) {
  const items: { label: string; variant: "domain" | "pos" | "construction" }[] = [];
  if (grammar_domain) {
    items.push({
      label: labelFor(taxonomy.grammar_domains, grammar_domain),
      variant: "domain",
    });
  }
  if (pos_tag && pos_tag !== "na" && pos_tag !== "multi") {
    items.push({ label: labelFor(taxonomy.pos_tags, pos_tag), variant: "pos" });
  }
  if (construction_type && construction_type !== "na") {
    items.push({
      label: labelFor(taxonomy.construction_types, construction_type),
      variant: "construction",
    });
  }
  if (!items.length) return null;
  const styles = {
    domain: "bg-violet-500/15 text-violet-200 border-violet-500/30",
    pos: "bg-sky-500/15 text-sky-200 border-sky-500/30",
    construction: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  };
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {items.map((item) => (
        <span
          key={item.label}
          className={`badge border text-[10px] uppercase tracking-wide ${styles[item.variant]}`}
        >
          {item.label}
        </span>
      ))}
    </div>
  );
}
