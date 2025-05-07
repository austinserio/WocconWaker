import json
from typing import Dict, List, Optional

# Import the enhanced analyzer
from woccon_morphological_analyzer import WocconMorphologicalAnalyzer

class WocconEnhancer:
    """
    Integration class to enhance the existing WocconT5 class with the new
    morphological analyzer based on Blair Rudes' research.
    """
    
    def __init__(self, woccon_t5, rules_path="woccon_language/rules.json"):
        """
        Initialize the enhancer with a reference to the existing WocconT5 instance
        and path to the updated rules.json
        """
        self.woccon_t5 = woccon_t5
        
        # Load the updated rules
        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)
        
        # Initialize the enhanced analyzer
        self.analyzer = WocconMorphologicalAnalyzer(self.rules)
        
        # Enhance the WocconT5 instance
        self._enhance_woccon_t5()
    
    def _enhance_woccon_t5(self):
        """
        Enhance the WocconT5 instance with new methods and override existing ones
        """
        # Add the analyzer as an attribute
        self.woccon_t5.morphological_analyzer = self.analyzer
        
        # Enhance the analyze_word method
        original_analyze_word = self.woccon_t5.analyze_word
        
        def enhanced_analyze_word(word: str) -> Dict:
            """
            Enhanced analyze_word method that combines original functionality
            with the new morphological analyzer
            """
            # Get the original analysis
            original_analysis = original_analyze_word(word)
            
            # Get the entry for meaning if available
            entry = self.woccon_t5.lookup_word(word, "woc_to_eng")
            meaning = entry["english"] if entry else ""
            
            # Get the enhanced analysis
            enhanced_analysis = self.analyzer.analyze_word(word, meaning)
            
            # Merge the analyses
            merged_analysis = original_analysis.copy()
            
            # Override roots with enhanced analysis if available
            if enhanced_analysis["roots"]:
                merged_analysis["roots"] = enhanced_analysis["roots"]
            
            # Add or merge affixes
            if "affixes" not in merged_analysis:
                merged_analysis["affixes"] = []
            
            # Create a set of existing affix forms
            existing_affix_forms = {affix["form"] for affix in merged_analysis["affixes"]}
            
            # Add new affixes that don't already exist
            for affix in enhanced_analysis["affixes"]:
                if affix["form"] not in existing_affix_forms:
                    merged_analysis["affixes"].append(affix)
                    existing_affix_forms.add(affix["form"])
            
            # Add new fields from enhanced analysis
            if enhanced_analysis["reduplication"]:
                merged_analysis["reduplication"] = enhanced_analysis["reduplication"]
            
            if enhanced_analysis["inflectional_mode"]:
                merged_analysis["inflectional_mode"] = enhanced_analysis["inflectional_mode"]
            
            if enhanced_analysis["syllable_structure"]:
                merged_analysis["syllable_structure"] = enhanced_analysis["syllable_structure"]
            
            return merged_analysis
        
        # Override the analyze_word method
        self.woccon_t5.analyze_word = enhanced_analyze_word
        
        # Add direct access to the analyzer's methods
        self.woccon_t5.identify_inflectional_mode = self.analyzer.identify_inflectional_mode
        self.woccon_t5.detect_reduplication = self.analyzer.detect_reduplication
        self.woccon_t5.analyze_prefixes = self.analyzer.analyze_prefixes
        self.woccon_t5.analyze_suffixes = self.analyzer.analyze_suffixes
        self.woccon_t5.analyze_roots = self.analyzer.analyze_roots

    def enhance_grammar_lesson_manager(self, grammar_lesson_manager):
        """
        Enhance the grammar lesson manager with new lesson items based on the updated rules
        """
        # Store reference to the original build_items method
        original_build_items = grammar_lesson_manager.build_items
        
        @staticmethod
        def enhanced_build_items(rules_json: Dict, lexicon: List[Dict]) -> List[Dict]:
            """Enhanced version of build_items with new lesson types"""
            # Get the original items
            items = original_build_items(rules_json, lexicon)
            
            # Add inflectional mode questions
            if "morphology" in rules_json and "inflectional_morphology" in rules_json["morphology"]:
                modes = rules_json["morphology"]["inflectional_morphology"].get("modes", [])
                for mode in modes:
                    items.append({
                        "type": "inflection_mode",
                        "question": f"What does the suffix **{mode['marker']}** indicate in Woccon?",
                        "answer": f"{mode['name']} mode ({mode['description']})"
                    })
                    
                    # Add example-based questions if examples exist
                    if "examples" in mode:
                        for example in mode["examples"]:
                            items.append({
                                "type": "mode_identify",
                                "question": f"What inflectional mode is used in the Woccon word **{example['form']}** ({example['gloss']})?",
                                "answer": f"{mode['name']} mode, marked by {mode['marker']}"
                            })
            
            # Add reduplication questions
            if "morphology" in rules_json and "reduplication" in rules_json["morphology"]:
                items.append({
                    "type": "reduplication",
                    "question": "What grammatical function does reduplication serve in Woccon?",
                    "answer": "Reduplication signals frequency or intensity"
                })
                
                if "examples" in rules_json["morphology"]["reduplication"]:
                    for example in rules_json["morphology"]["reduplication"]["examples"]:
                        items.append({
                            "type": "reduplication_example",
                            "question": f"The Woccon word **{example['word']}** ({example['gloss']}) shows what morphological pattern?",
                            "answer": f"Reduplication - {example['derivation']}"
                        })
            
            # Add questions about common roots if they exist
            if "morphology" in rules_json and "common_roots" in rules_json["morphology"]:
                for root in rules_json["morphology"]["common_roots"]:
                    items.append({
                        "type": "root_meaning",
                        "question": f"What is the meaning of the Woccon root **{root['root']}**?",
                        "answer": root['meaning']
                    })
                    
                    # Add derivative questions if derivatives exist
                    if "derivatives" in root and root["derivatives"]:
                        for derivative in root["derivatives"][:1]:  # Just one example per root
                            items.append({
                                "type": "root_derivative",
                                "question": f"The Woccon word **{derivative['form']}** contains which root?",
                                "answer": f"{root['root']} meaning '{root['meaning']}'"
                            })
            
            return items
        
        # Override the build_items method
        grammar_lesson_manager.build_items = enhanced_build_items
    
    def enhance_lesson_manager(self, lesson_manager):
        """
        Enhance the regular lesson manager with morphological context for vocabulary lessons
        """
        # Define a new method to add linguistic context to vocabulary items
        def _add_linguistic_context(self, word_entry):
            """Add linguistic context to a word based on morphological analysis"""
            word = word_entry['woccon']
            
            # Get analysis if parent exists and has woccon attribute
            analysis = {}
            if self.parent and hasattr(self.parent, 'woccon'):
                try:
                    analysis = self.parent.woccon.analyze_word(word)
                except Exception as e:
                    print(f"Error analyzing word {word}: {e}")
            
            context = []
            
            # Add root information
            if "roots" in analysis and analysis["roots"]:
                for root in sorted(analysis["roots"], key=lambda x: x.get("confidence_score", 0), reverse=True):
                    if root.get("confidence") not in ["low"]:
                        context.append(f"• Contains the root **{root['root']}** meaning '{root['meaning']}'")
                        break
            
            # Add affix information
            if "affixes" in analysis and analysis["affixes"]:
                for affix in analysis["affixes"]:
                    context.append(f"• Contains the {affix['type']} **{affix['form']}** ({affix['function']})")
            
            # Add reduplication information
            if "reduplication" in analysis and analysis["reduplication"]:
                context.append(f"• Shows {analysis['reduplication']['type']} pattern indicating {analysis['reduplication']['pattern']}")
            
            # Add inflectional mode information if relevant
            if "inflectional_mode" in analysis and analysis["inflectional_mode"]:
                infl_mode = analysis["inflectional_mode"]
                if infl_mode["mode"] != "unknown":
                    context.append(f"• Uses the {infl_mode['mode']} mode marked by {infl_mode['marker']}")
            
            if not context:
                context.append("• No additional morphological information available")
            
            return "\n".join(context)
        
        # Add the method to the lesson manager
        lesson_manager._add_linguistic_context = _add_linguistic_context.__get__(lesson_manager)
        
        # Store reference to the original prompt method
        original_prompt = lesson_manager.prompt
        
        def enhanced_prompt(self):
            """Enhanced prompt method that adds linguistic context"""
            # Get the original prompt
            prompt_text = original_prompt(self)
            
            # If we're in the "reveal" stage or similar, add linguistic context
            if self.i < len(self.words) and hasattr(self, '_add_linguistic_context'):
                w = self.words[self.i]
                
                # Only add context in certain situations
                if "✅ Correct!" in prompt_text or "The correct answer is" in prompt_text:
                    # Add linguistic context
                    context = self._add_linguistic_context(w)
                    
                    # Insert before the "next" instruction if present
                    if "\n\n" in prompt_text:
                        parts = prompt_text.split("\n\n", 1)
                        prompt_text = f"{parts[0]}\n\n📚 **Linguistic Context:**\n{context}\n\n{parts[1]}"
                    else:
                        prompt_text += f"\n\n📚 **Linguistic Context:**\n{context}"
            
            return prompt_text
        
        # Override the prompt method
        lesson_manager.prompt = enhanced_prompt.__get__(lesson_manager)

# Example usage:
"""
from main import WocconT5
from grammar_lesson_manager import GrammarLessonManager
from lesson_manager import LessonManager
from woccon_enhancer import WocconEnhancer

# Initialize original WocconT5
woccon = WocconT5()

# Enhance it with the new analyzer
enhancer = WocconEnhancer(woccon, rules_path="woccon_language/rules.json")

# When creating lesson managers, they will automatically use the enhanced functionality
grammar_lesson_manager = GrammarLessonManager(...)
enhancer.enhance_grammar_lesson_manager(grammar_lesson_manager)

lesson_manager = LessonManager(...)
enhancer.enhance_lesson_manager(lesson_manager)
"""