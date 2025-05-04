"""
Modified prompt templates for the Woccon language revitalization T5 model.
Focused on analyzing existing words rather than generating new content.
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
    
    def word_lookup_prompt(self, search_term: str) -> str:
        """
        Template for looking up a Woccon word or English meaning
        """
        # Check if this is a Woccon word first
        is_woccon_word = any(word["woccon"].lower() == search_term.lower() for word in self.dictionary.get("lexicon", []))
        
        if is_woccon_word:
            search_direction = "Woccon to English"
            direction_note = "Find the English meaning of this Woccon word."
        else:
            search_direction = "English to Woccon"
            direction_note = "Find Woccon words that match this English meaning."
        
        prompt = f"""Look up the following term in the Woccon language dictionary:

Search term: "{search_term}"
Search direction: {search_direction}
Task: {direction_note}

Provide the complete dictionary entry including part of speech, and note whether 
this is an exact match or a partial match.

Dictionary lookup result:"""

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
        pos = word_info["pos"] if word_info else "unknown"
        
        # Get relevant roots that might be in this word
        possible_roots = []
        for root_name, root_info in self.roots.items():
            root_clean = root_name.rstrip('-')
            if woccon_word.lower().startswith(root_clean) or f"-{root_clean}" in woccon_word.lower():
                possible_roots.append(f"{root_name} = {root_info['meaning']}")
                
        roots_text = "\n".join(possible_roots) if possible_roots else "No known roots identified."
        
        # Get known affixes that might be in this word
        known_suffixes = ["-wa", "-he", "-iune", "-pe"]
        suffix_info = []
        
        for suffix in known_suffixes:
            clean_suffix = suffix.lstrip("-")
            if woccon_word.lower().endswith(clean_suffix):
                if suffix == "-wa":
                    suffix_info.append(f"{suffix} = indicates natural phenomena (rain, snow)")
                elif suffix == "-he":
                    suffix_info.append(f"{suffix} = nominal suffix for animate beings (Indians, dog)")
                elif suffix == "-iune":
                    suffix_info.append(f"{suffix} = indicates manufactured items (blankets)")
                elif suffix == "-pe":
                    suffix_info.append(f"{suffix} = indicates containers (bottle, gourd)")
                    
        suffix_text = "\n".join(suffix_info) if suffix_info else "No known suffixes identified."
        
        # Find related words with the same root
        related_words = []
        if possible_roots:
            first_root = possible_roots[0].split("=")[0].strip().rstrip('-')
            for word in self.dictionary.get("lexicon", []):
                if word["woccon"].lower() != woccon_word.lower() and word["woccon"].lower().startswith(first_root):
                    related_words.append(f"{word['woccon']} = {word['english']}")
        
        related_text = "\n".join(related_words[:5]) if related_words else "No clearly related words identified."
        
        prompt = f"""Analyze the structure of the Woccon word using linguistic principles:

Word: {woccon_word}
Meaning: {meaning}
Part of speech: {pos}

Possible roots:
{roots_text}

Possible suffixes:
{suffix_text}

Related words with similar roots:
{related_text}

Analyze the morphological structure, possible root-affix combinations, and any 
sound patterns in this word. Provide the most likely breakdown of this word's structure.

Morphological analysis:"""

        return prompt
    
    def category_browse_prompt(self, category: str) -> str:
        """
        Template for browsing words by semantic category
        """
        # Define category patterns
        category_keywords = {
            "animals": ["fish", "snake", "bird", "dog", "wolf", "squirrel", "panther"],
            "water": ["water", "rain", "fish", "river", "stream", "wet"],
            "clothing": ["cloth", "blanket", "shirt", "wear", "breech", "stocking", "hide", "skin", "buckskin"],
            "containers": ["container", "bottle", "bowl", "basket", "box", "gourd"],
            "body_parts": ["head", "hand", "body", "foot", "hair", "face"],
            "natural_elements": ["tree", "wood", "fire", "stone", "rock", "earth"],
            "tools": ["tool", "knife", "axe", "spoon", "hoe", "needle", "gunpowder", "weapon"],
            "cultural": ["indian", "chief", "warrior", "spirit", "ceremony", "hominy", "skin", "hide", "buckskin"]
        }
        
        # Handle category aliases
        category_map = {
            "animal": "animals",
            "water_related": "water",
            "nature": "natural_elements",
            "weapon": "tools",
            "culture": "cultural",
            "body": "body_parts",
            "container": "containers"
        }
        
        # Normalize category name
        norm_category = category.lower()
        if norm_category in category_map:
            norm_category = category_map[norm_category]
            
        # Find keywords for this category
        keywords = category_keywords.get(norm_category, [])
        if not keywords:
            # If category not found, list available categories
            available = ", ".join(list(category_keywords.keys()))
            prompt = f"""The category "{category}" is not recognized. 

Available categories are: {available}

Please specify one of the available categories to browse Woccon words in that semantic domain.

Category browse results:"""
            return prompt
            
        # Find words matching this category
        matching_words = []
        for word in self.dictionary.get("lexicon", []):
            eng = word["english"].lower()
            if any(keyword in eng for keyword in keywords):
                matching_words.append(word)
                
        words_text = "\n".join([f"- {w['woccon']} = {w['english']} ({w['pos']})" for w in matching_words])
        
        prompt = f"""Browse Woccon words in the following semantic category:

Category: {category} ({norm_category})
Keywords: {', '.join(keywords)}

List all Woccon words in this category with their meanings and parts of speech.

Category browse results:
{words_text}

Summary: Found {len(matching_words)} words in the {norm_category} category."""

        return prompt
    
    def sound_correspondence_prompt(self, catawba_word: str) -> str:
        """
        Template for analyzing how a Catawba word might correspond to Woccon
        """
        correspondence_text = self.get_sound_correspondences()
        
        prompt = f"""Analyze how the Catawba word would likely correspond to a Woccon form:

Catawba word: {catawba_word}

{correspondence_text}

Apply the sound correspondence rules systematically to explain how this Catawba word 
would likely appear in Woccon based on historical sound changes between the languages.

Correspondence analysis:"""

        return prompt
    
    def language_info_prompt(self) -> str:
        """
        Template for providing information about the Woccon language
        """
        prompt = f"""Provide educational information about the Woccon language:

Compile key information about the Woccon language, including:
1. Historical and geographical context
2. Linguistic classification and relationships
3. Known vocabulary size and sources
4. Key grammatical features based on available evidence
5. Current status and revitalization efforts

Format the information as an educational overview suitable for language learners.

Woccon language information:"""

        return prompt
    
    def generate_all_examples(self) -> Dict[str, str]:
        """Generate example prompts for all template types"""
        examples = {}
        
        # Word lookup example
        examples["word_lookup"] = self.word_lookup_prompt("yau")
        
        # Word analysis example
        examples["word_analysis"] = self.word_analysis_prompt("yawowa")
        
        # Category browse example
        examples["category_browse"] = self.category_browse_prompt("animals")
        
        # Sound correspondence example
        examples["sound_correspondence"] = self.sound_correspondence_prompt("tasi")
        
        # Language info example
        examples["language_info"] = self.language_info_prompt()
        
        return examples


# Example usage
if __name__ == "__main__":
    generator = WocconPromptGenerator("dictionary.json", "rules.json")
    
    # Generate and display example prompts
    examples = generator.generate_all_examples()
    
    print("=== EXAMPLE PROMPTS ===\n")
    for prompt_type, prompt in examples.items():
        print(f"--- {prompt_type.upper()} PROMPT ---")
        print(prompt)
        print("\n" + "="*50 + "\n")