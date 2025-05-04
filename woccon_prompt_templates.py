"""
Prompt templates for the Woccon language revitalization T5 model.
These templates are designed to be filled with specific grammar rules
and examples from the Woccon language data.
"""

import json
import random
from typing import Dict, List, Tuple, Optional, Union

class WocconPromptGenerator:
    def __init__(self, dictionary_path: str, rules_path: str):
        """Initialize with paths to the dictionary and rules JSON files"""
        # Load dictionary and rules
        with open(dictionary_path, 'r', encoding='utf-8') as f:
            self.dictionary = json.load(f)
        
        with open(rules_path, 'r', encoding='utf-8') as f:
            self.rules = json.load(f)
            
        # Organize words by part of speech for easy lookup
        self.words_by_pos = self._organize_by_pos()
        
        # Extract key linguistic patterns
        self.roots = {root["root"]: root for root in self.dictionary.get("common_roots", [])}
        self.affixes = self._extract_affixes()
        
    def _organize_by_pos(self) -> Dict[str, List[Dict]]:
        """Organize the lexicon by part of speech"""
        by_pos = {}
        for word in self.dictionary.get("lexicon", []):
            pos = word.get("pos")
            if pos not in by_pos:
                by_pos[pos] = []
            by_pos[pos].append(word)
        return by_pos
    
    def _extract_affixes(self) -> Dict[str, List[Dict]]:
        """Extract affixes from the rules file"""
        affixes = {"prefix": [], "suffix": []}
        
        # Extract from morphology section if it exists
        morphology = self.rules.get("morphology", {})
        if "affixes" in morphology:
            for affix_type, affix_list in morphology["affixes"].items():
                if "suffixes" in affix_type.lower():
                    for affix in affix_list:
                        affixes["suffix"].append(affix)
                elif "prefixes" in affix_type.lower():
                    for affix in affix_list:
                        affixes["prefix"].append(affix)
        
        return affixes
    
    def get_random_example(self, pos: Optional[str] = None) -> Dict:
        """Get a random word from the lexicon, optionally filtering by part of speech"""
        if pos and pos in self.words_by_pos:
            return random.choice(self.words_by_pos[pos])
        else:
            return random.choice(self.dictionary.get("lexicon", []))
    
    def get_related_words(self, root: str) -> List[Dict]:
        """Get words that contain a specific root"""
        related = []
        root_clean = root.rstrip('-')
        
        for word in self.dictionary.get("lexicon", []):
            # More precise check - look for the root at the beginning of the word
            # or as a clear component with a hyphen
            woccon_word = word["woccon"].lower()
            if (woccon_word.startswith(root_clean) or 
                f"-{root_clean}" in woccon_word or 
                f"{root_clean}-" in woccon_word):
                related.append(word)
                
        return related
    
    def get_sound_correspondences(self) -> str:
        """Get a formatted string of sound correspondences between Woccon and Catawba"""
        correspondences = self.dictionary.get("sound_correspondences", {}).get("woccon_to_catawba", [])
        
        if not correspondences:
            return "No sound correspondence data available."
            
        result = "Sound Correspondences between Woccon and Catawba:\n"
        for corr in correspondences:
            examples = corr.get("examples", [])
            example_text = f" (Examples: {', '.join(examples)})" if examples else ""
            result += f"- Woccon '{corr['woccon']}' corresponds to Catawba '{corr['catawba']}'{example_text}\n"
            
        return result
            
    def translate_prompt(self, english_text: str) -> str:
        """
        Template for English-to-Woccon translation prompts
        """
        # Get some relevant grammar rules to include
        phonology_rules = "Woccon has the following consonants: p, t, k, m, n, r, s, h, w, y."
        morphology_example = "Common roots include: ya- (water), roo- (cloth/hide), yau- (path), watta- (container)"
        
        # Find similar words if possible
        keywords = english_text.lower().split()
        similar_examples = []
        
        for word in self.dictionary.get("lexicon", []):
            eng = word["english"].lower()
            for keyword in keywords:
                if keyword in eng and len(keyword) > 2:  # Only match substantial keywords
                    similar_examples.append(f"{word['woccon']} = {word['english']}")
                    break
                    
        examples_text = "\nSimilar vocabulary:\n" + "\n".join(similar_examples) if similar_examples else ""
                    
        prompt = f"""Translate the English text to Woccon language using the following rules:

{phonology_rules}
{morphology_example}
{examples_text}

English text: "{english_text}"
Woccon translation:"""

        return prompt
    
    def word_analysis_prompt(self, woccon_word: str) -> str:
        """
        Template for analyzing the structure of a Woccon word
        """
        # Look up the word to get its meaning
        word_info = None
        for word in self.dictionary.get("lexicon", []):
            if word["woccon"].lower() == woccon_word.lower():
                word_info = word
                break
                
        meaning = word_info["english"] if word_info else "unknown"
        
        # Get relevant roots that might be in this word
        possible_roots = []
        for root_name, root_info in self.roots.items():
            if root_name.rstrip('-') in woccon_word.lower():
                possible_roots.append(f"{root_name} = {root_info['meaning']}")
                
        roots_text = "\n".join(possible_roots) if possible_roots else "No known roots identified."
        
        prompt = f"""Analyze the structure of the Woccon word using linguistic principles:

Word: {woccon_word}
Meaning: {meaning}

Possible roots:
{roots_text}

Analyze the morphological structure, possible root-affix combinations, and any 
sound patterns in this word. Provide the most likely breakdown of this word's structure.

Morphological analysis:"""

        return prompt
    
    def word_generation_prompt(self, meaning: str, root: Optional[str] = None) -> str:
        """
        Template for generating a new Woccon word based on a meaning
        """
        # Get related words that might serve as examples
        related_words = []
        
        if root:
            root_words = self.get_related_words(root)
            related_text = "\n".join([f"{w['woccon']} = {w['english']}" for w in root_words])
            root_info = f"Requested root: {root}\nWords with this root:\n{related_text}"
        else:
            # Find similar semantic domain
            keywords = meaning.lower().split()
            for word in self.dictionary.get("lexicon", []):
                eng = word["english"].lower()
                for keyword in keywords:
                    if keyword in eng and len(keyword) > 2:
                        related_words.append(word)
                        break
            
            # Try to identify an appropriate root
            semantic_domains = {
                "water": ["water", "rain", "fish", "wet"],
                "cloth": ["cloth", "clothing", "hide", "blanket"],
                "path": ["path", "way", "road", "Indians"],
                "container": ["container", "bottle", "vessel", "gourd"],
                "wood": ["wood", "tree", "box"]
            }
            
            suggested_root = None
            for domain, terms in semantic_domains.items():
                if any(term in meaning.lower() for term in terms):
                    if domain == "water":
                        suggested_root = "ya-"
                    elif domain == "cloth":
                        suggested_root = "roo-"
                    elif domain == "path":
                        suggested_root = "yau-"
                    elif domain == "container":
                        suggested_root = "watta-"
                    elif domain == "wood":
                        suggested_root = "yon-"
                    break
                    
            if suggested_root:
                root_words = self.get_related_words(suggested_root)
                related_text = "\n".join([f"{w['woccon']} = {w['english']}" for w in root_words])
                root_info = f"Suggested root: {suggested_root}\nWords with this root:\n{related_text}"
            else:
                related_text = "\n".join([f"{w['woccon']} = {w['english']}" for w in related_words[:5]])
                root_info = f"Similar words in vocabulary:\n{related_text}"
        
        # Add some affix examples
        affix_examples = []
        for affix in self.affixes.get("suffix", []):
            if "form" in affix and "function" in affix:
                affix_examples.append(f"{affix['form']} = {affix['function']}")
        
        affix_text = "\nCommon suffixes:\n" + "\n".join(affix_examples) if affix_examples else ""
        
        prompt = f"""Generate a new Woccon word for the following meaning using linguistic principles:

Requested meaning: "{meaning}"

{root_info}
{affix_text}

The sound patterns of Woccon include: p, t, k, m, n, r, s, h, w, y
Common word structures include: root+suffix, compound nouns

Generate a plausible Woccon word:"""

        return prompt
    
    def sound_correspondence_prompt(self, catawba_word: str) -> str:
        """
        Template for converting a Catawba word to its likely Woccon equivalent
        """
        correspondence_text = self.get_sound_correspondences()
        
        prompt = f"""Convert the Catawba word to its likely Woccon equivalent using sound correspondence rules:

Catawba word: {catawba_word}

{correspondence_text}

Apply the sound correspondence rules systematically to generate the most 
likely Woccon equivalent of this Catawba word.

Woccon equivalent:"""

        return prompt
    
    def sentence_structure_prompt(self, english_sentence: str) -> str:
        """
        Template for generating Woccon sentence structure based on limited evidence
        """
        # Extract key words from the sentence to find vocabulary
        words = english_sentence.lower().replace("?", "").replace(".", "").replace(",", "").split()
        found_words = []
        
        for word in words:
            if len(word) > 2:  # Skip short function words
                for dict_word in self.dictionary.get("lexicon", []):
                    if word in dict_word["english"].lower():
                        found_words.append(dict_word)
                        break
        
        vocab_text = "\n".join([f"{w['woccon']} = {w['english']}" for w in found_words])
        vocab_section = f"Relevant vocabulary:\n{vocab_text}" if found_words else "No direct vocabulary matches found."
        
        # Add example phrases from the dictionary if available
        phrases = self.dictionary.get("phrases", [])
        phrase_text = ""
        if phrases:
            phrase_examples = "\n".join([f"{p['woccon']} = {p['english']}" for p in phrases])
            phrase_text = f"\nExample phrases in Woccon:\n{phrase_examples}"
        
        prompt = f"""Construct a plausible Woccon sentence structure for the following English sentence:

English: "{english_sentence}"

{vocab_section}
{phrase_text}

Based on limited evidence, Woccon likely follows subject-verb-object order similar to other Siouan languages.
Use the available vocabulary and phrase patterns to construct a plausible Woccon sentence.

Woccon sentence:"""

        return prompt
    
    def generate_all_examples(self) -> Dict[str, str]:
        """Generate example prompts for all template types"""
        examples = {}
        
        # Translation example
        examples["translation"] = self.translate_prompt("The fire is hot")
        
        # Word analysis example
        examples["word_analysis"] = self.word_analysis_prompt("yawowa")
        
        # Word generation example
        examples["word_generation"] = self.word_generation_prompt("river", root="ya-")
        
        # Sound correspondence example
        examples["sound_correspondence"] = self.sound_correspondence_prompt("tasi")
        
        # Sentence structure example
        examples["sentence_structure"] = self.sentence_structure_prompt("The dog sees the fire")
        
        return examples


# Example usage
if __name__ == "__main__":
    generator = WocconPromptGenerator("woccon_language/dictionary.json", "woccon_language/rules.json")
    
    # Generate and display example prompts
    examples = generator.generate_all_examples()
    
    print("=== EXAMPLE PROMPTS ===\n")
    for prompt_type, prompt in examples.items():
        print(f"--- {prompt_type.upper()} PROMPT ---")
        print(prompt)
        print("\n" + "="*50 + "\n")