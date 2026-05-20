import { TaxonomyOption, labelFor } from "./taxonomy";

export interface LexiconTaxonomy {
  teaching_units: TaxonomyOption[];
  word_classes: TaxonomyOption[];
  lesson_bands: TaxonomyOption[];
}

export { labelFor };
