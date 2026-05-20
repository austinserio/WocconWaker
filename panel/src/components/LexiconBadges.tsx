import { labelFor, LexiconTaxonomy } from "../lexiconTaxonomy";

export function LexiconBadges({
  taxonomy,
  teaching_unit,
  word_class,
  lesson_band,
}: {
  taxonomy: LexiconTaxonomy;
  teaching_unit?: string | null;
  word_class?: string | null;
  lesson_band?: string | null;
}) {
  const items: { label: string; variant: "unit" | "class" | "band" }[] = [];
  if (teaching_unit && teaching_unit !== "other") {
    items.push({
      label: labelFor(taxonomy.teaching_units, teaching_unit),
      variant: "unit",
    });
  }
  if (word_class && word_class !== "unknown") {
    items.push({ label: labelFor(taxonomy.word_classes, word_class), variant: "class" });
  }
  if (lesson_band) {
    items.push({ label: labelFor(taxonomy.lesson_bands, lesson_band), variant: "band" });
  }
  if (!items.length) return null;
  const styles = {
    unit: "bg-amber-500/15 text-amber-200 border-amber-500/30",
    class: "bg-sky-500/15 text-sky-200 border-sky-500/30",
    band: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
  };
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {items.map((item) => (
        <span
          key={`${item.variant}-${item.label}`}
          className={`badge border text-[10px] uppercase tracking-wide ${styles[item.variant]}`}
        >
          {item.label}
        </span>
      ))}
    </div>
  );
}
