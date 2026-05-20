export interface TaxonomyOption {
  id: string;
  label: string;
  description?: string;
}

export interface Taxonomy {
  grammar_domains: TaxonomyOption[];
  pos_tags: TaxonomyOption[];
  construction_types: TaxonomyOption[];
  note_categories: string[];
}

export function labelFor(options: TaxonomyOption[], id?: string | null): string {
  if (!id) return "";
  return options.find((o) => o.id === id)?.label ?? id.replace(/_/g, " ");
}
