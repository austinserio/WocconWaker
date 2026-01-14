"""
WocconWaker Improvements Integration

This module integrates the fact-checking guard rails with the WocconWaker system
to prevent fabrication of linguistic features and ensure accuracy.
"""

import re
import json
import logging
import random
from typing import Dict, List, Tuple, Optional, Any

# Import the fact validator
from woccon_guard_rail import WocconFactValidator

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("woccon_enhancements")

class OrthographicAccuracyEnhancer:
    """
    Enhances the WocconAssistant with fact-checking capabilities and 
    prevents hallucination of diacritical marks.
    """
    
    def __init__(self, dict_path="woccon_language/dictionary.json", 
                 rules_path="woccon_language/rules.json"):
        """
        Initialize the enhancer with paths to the dictionary and rules files.
        
        Args:
            dict_path: Path to the dictionary JSON file
            rules_path: Path to the rules JSON file
        """
        self.dict_path = dict_path
        self.rules_path = rules_path
        
        # Initialize the fact validator
        self.validator = WocconFactValidator(dict_path, rules_path)
        
        # Load the dictionary and rules
        self.dictionary = self._load_json(dict_path)
        self.rules = self._load_json(rules_path)
        
        # Extract the actual orthography used in Woccon
        self.orthography = self._extract_orthography()
        
        log.info("OrthographicAccuracyEnhancer initialized")
    
    def _load_json(self, path: str) -> Dict:
        """Load JSON data from a file."""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _extract_orthography(self) -> Dict:
        """Extract the actual orthography used in Woccon documentation."""
        # Get all attested Woccon words
        attested_words = [entry["woccon"] for entry in self.dictionary.get("lexicon", [])]
        
        # Get all letters used in Woccon words
        all_letters = set()
        for word in attested_words:
            for char in word:
                all_letters.add(char)
        
        # Identify special characters (non-alphanumeric)
        special_chars = {c for c in all_letters if not (c.isalnum() or c.isspace())}
        
        return {
            "alphabet": sorted(list(all_letters)),
            "special_characters": sorted(list(special_chars))
        }
    
    def enhance_woccon_assistant(self, assistant):
        """
        Enhance a WocconAssistant instance with fact-checking.
        
        Args:
            assistant: The WocconAssistant instance to enhance
        """
        # Store reference to the original reply method
        original_reply = assistant.reply
        
        # Create an enhanced reply method
        def enhanced_reply(user_id: str, text: str) -> str:
            """Enhanced reply method with fact-checking."""
            # Get the original reply
            original_response = original_reply(user_id, text)
            
            # Validate the response with the fact validator
            processed = self.validator.process_response(original_response)
            
            if processed.get("needs_correction", False):
                # Log that a correction was needed
                correction = processed.get("correction", "")
                log.info(f"Fact check applied: {correction}")
                
                # Use the suggested corrected response
                return processed.get("suggested_response", original_response)
            
            # Return the enhanced response (might have disclaimer added)
            return processed.get("enhanced_response", original_response)
        
        # Replace the reply method
        assistant.reply = enhanced_reply
        log.info("Enhanced WocconAssistant's reply method with fact checking")
        
        # Enhance the _strict_verify method to be more strict
        original_verify = getattr(assistant, '_strict_verify', None)
        
        if original_verify is None:
            log.warning("WocconAssistant doesn't have _strict_verify method, skipping verification enhancement")
        else:
            def enhanced_verify(text: str, has_strong_match: bool = True, is_word_request: bool = False) -> str:
                """Enhanced verification that also checks for diacritical marks."""
                # First run the original verification
                verified_text = original_verify(text, has_strong_match, is_word_request)
                
                # Then check for diacritical marks in Woccon words
                diacritical_regex = r"[çćĉċčřŕŗřśŝşšșẋỳŷỹȳāăąēĕėęěīĭįőōĩĕẽã]"
                
                # Look for claims of Woccon words with diacritical marks
                woccon_claim_patterns = [
                    r"Woccon word (?:for|is) ['\"]([a-zA-Z\-" + diacritical_regex + r"]+)['\"]",
                    r"in Woccon, ['\"]([a-zA-Z\-" + diacritical_regex + r"]+)['\"]",
                    r"Woccon term ['\"]([a-zA-Z\-" + diacritical_regex + r"]+)['\"]"
                ]
                
                for pattern in woccon_claim_patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        return (
                            "⚠️ Note: The original Woccon transcription by John Lawson (1709) "
                            "does not use diacritical marks. Modern linguistic notation may use "
                            "special symbols, but these were not part of the original documentation.\n\n" 
                            + verified_text
                        )
                
                return verified_text
            
            # Replace the verification method
            assistant._strict_verify = enhanced_verify
            log.info("Enhanced WocconAssistant's verification method")
        
        return assistant

    def get_enhanced_responses(self) -> Dict[str, str]:
        """
        Get factually accurate responses for common Woccon language questions.
        
        Returns:
            A dictionary of question types to accurate responses
        """
        return {
            "orthography": self._get_orthography_response(),
            "phonology": self._get_phonology_response(),
            "grammar": self._get_grammar_response(),
            "vocabulary": self._get_vocabulary_response(),
            "number_system": self._get_number_system_response(),
            "general_info": self._get_general_info_response()
        }
    
    def _get_orthography_response(self) -> str:
        """Get a factually accurate response about Woccon orthography."""
        return f"""The Woccon language as documented by John Lawson in 1709 was written using standard Latin alphabet characters. Lawson's transcription doesn't use any special diacritical marks, as this was a simple word list recorded using English spelling conventions of the early 18th century.

The characters that appear in the Woccon word list include: {', '.join(self.orthography['alphabet'])}

Some special characters occasionally used include: {', '.join(self.orthography['special_characters']) if self.orthography['special_characters'] else 'none (only standard Latin letters, numbers, and spaces)'}

It's important to understand that modern linguistic analyses of Woccon (based on comparing it with related Siouan languages like Catawba) might use special phonetic symbols from the International Phonetic Alphabet (IPA) to represent sounds more accurately. These include symbols for nasal vowels (ĩ, ẽ, ã, ũ) and palatalized consonants (č, š, ś), but these are scholarly conventions and were not part of Lawson's original documentation.

When reading Woccon words from Lawson's list, you should pronounce them using the approximate English values of the letters as they would have been used in the early 1700s."""
    
    def _get_phonology_response(self) -> str:
        """Get a factually accurate response about Woccon phonology."""
        # Extract phonological information from rules
        vocalic_phonemes = self.rules.get("phonology", {}).get("vocalic_phonemes", {})
        consonantal_phonemes = self.rules.get("phonology", {}).get("consonantal_phonemes", [])
        
        short_vowels = vocalic_phonemes.get("short_oral_vowels", [])
        long_vowels = vocalic_phonemes.get("long_oral_vowels", [])
        nasal_vowels = vocalic_phonemes.get("nasal_vowels", [])
        
        consonants = [c.get("grapheme", "") for c in consonantal_phonemes]
        
        return f"""Based on linguistic analysis of the Woccon word list and comparison with related languages, scholars believe the Woccon phonological system likely included:

1. Vowels:
   - Short oral vowels: {', '.join(short_vowels)}
   - Long oral vowels: {', '.join(long_vowels)}
   - Nasal vowels: {', '.join(nasal_vowels)}

2. Consonants: {', '.join(consonants)}

It's important to note that this phonological reconstruction is based on comparative linguistic analysis, as John Lawson's 1709 documentation only provides the words written using English orthographic conventions of that time, without special phonetic notation.

Lawson's transcription gives us clues about the sounds of Woccon, but the exact pronunciation remains a subject of scholarly reconstruction through comparison with related languages like Catawba.

[Note: Our knowledge of Woccon is limited to John Lawson's 1709 word list containing 143 items. Any descriptions of pronunciation or phonology beyond this documented evidence should be treated as scholarly reconstruction rather than established fact.]"""
    
    def _get_grammar_response(self) -> str:
        """Get a factually accurate response about Woccon grammar."""
        return """Our knowledge of Woccon grammar is very limited since we only have a word list rather than complete sentences or texts. However, by analyzing the words and comparing with related languages like Catawba, linguists have made some observations about Woccon grammar:

1. Word structure: Many Woccon words show evidence of being constructed from roots and affixes (prefixes and suffixes).

2. Common roots: Several recurring elements appear across multiple words, suggesting a system of word formation from base elements. For example, "roo-" appears in words related to cloth or materials.

3. Compounding: Words can be formed by combining multiple roots, as in "yauh-he" (Indians) which combines "yauh" (path) with the animate suffix "-he".

4. Number system: The Woccon number system shows a possible partial quinary (base-5) structure with decimal influence.

It's important to note that these grammatical observations are based on limited evidence and scholarly reconstruction. Without complete sentences or texts in Woccon, our understanding of its grammar remains incomplete.

[Note: Our knowledge of Woccon is limited to John Lawson's 1709 word list containing 143 items. Any descriptions of grammar or language structure beyond this documented evidence should be treated as scholarly reconstruction rather than established fact.]"""
    
    def _get_vocabulary_response(self) -> str:
        """Get a factually accurate response about Woccon vocabulary."""
        # Get a random selection of words to show as examples
        lexicon = self.dictionary.get("lexicon", [])
        sample_size = min(5, len(lexicon))
        samples = random.sample(lexicon, sample_size)
        
        sample_text = "\n".join([f"- {w['woccon']} ({w['pos']}): {w['english']}" for w in samples])
        
        return f"""The Woccon vocabulary we know comes entirely from John Lawson's word list from 1709, which contains 143 documented words. Here are a few examples from the list:

{sample_text}

The vocabulary includes words for body parts, animals, numbers, natural elements, and everyday objects. We can see some patterns in word formation, such as the common root "roo-" appearing in words related to cloth or material.

If you'd like to learn some Woccon vocabulary through an interactive lesson, just let me know!"""
    
    def _get_number_system_response(self) -> str:
        """Get a factually accurate response about the Woccon number system."""
        number_system = self.dictionary.get("number_system", {})
        numbers = number_system.get("numbers", [])
        
        # Format numbers
        number_text = "\n".join([f"{n.get('value', '')}: {n.get('form', '')}" for n in numbers])
        
        pattern = number_system.get("pattern", "unknown")
        structure_notes = number_system.get("structure_notes", [])
        structure_text = "\n".join([f"- {note}" for note in structure_notes])
        
        return f"""The Woccon number system as documented by Lawson in 1709 shows evidence of a {pattern} pattern. Here are the known Woccon numbers:

{number_text}

Linguists have observed some interesting patterns:
{structure_text}

This number system shows similarities to those found in related Siouan languages, particularly Catawba."""
    
    def _get_general_info_response(self) -> str:
        """Get a factually accurate general response about Woccon."""
        return """Woccon was an Eastern Siouan (Coastal Catawban) language historically spoken in the North Carolina coastal plain along the lower Neuse River. Our knowledge of Woccon comes primarily from a word list of 143 items collected by John Lawson in 1709.

The Woccon tribe was first documented in 1701 by Lawson, with an estimated population of 500-600 individuals. They lived about two leagues east of the southern villages of the Tuscarora tribe, near present-day Goldsboro/Snow Hill (Wayne/Greene County). The tribe was last mentioned in a 1712 treaty and was likely absorbed by the Tuscarora following the Tuscarora wars of 1711-1713.

Woccon is related to Catawba and other Eastern Siouan languages. Analysis of vocabulary shows connections with Catawba, though the languages had diverged significantly.

I can provide more specific information about Woccon vocabulary, pronunciation, or number system if you're interested in a particular aspect of the language."""

class FactualGuardRailIntegration:
    """
    Integration class to apply the OrthographicAccuracyEnhancer to various Woccon components.
    """
    
    def __init__(self, dict_path="woccon_language/dictionary.json", 
                 rules_path="woccon_language/rules.json"):
        """
        Initialize the integration with paths to the dictionary and rules files.
        
        Args:
            dict_path: Path to the dictionary JSON file
            rules_path: Path to the rules JSON file
        """
        self.enhancer = OrthographicAccuracyEnhancer(dict_path, rules_path)
    
    def enhance_assistant(self, assistant):
        """Enhance a WocconAssistant instance."""
        return self.enhancer.enhance_woccon_assistant(assistant)
    
    def enhance_cli(self, cli_instance):
        """Enhance a WocconCLI instance."""
        # Replace response methods with fact-checked versions
        responses = self.enhancer.get_enhanced_responses()
        
        # For a CLI, we'll need to patch individual handler methods
        if hasattr(cli_instance, 'show_language_info'):
            original_info = cli_instance.show_language_info
            cli_instance.show_language_info = lambda: responses.get("general_info", original_info())
        
        return cli_instance

    def enhance_woccon_t5(self, woccon_t5):
        """Enhance a WocconT5 instance to prevent hallucination."""
        # Store reference to the original analyze_word method
        original_analyze = woccon_t5.analyze_word
        
        def enhanced_analyze_word(word: str) -> Dict:
            """Enhanced analyze_word method to ensure factual accuracy."""
            # Get the original analysis
            analysis = original_analyze(word)
            
            # Check for diacritical marks in the word being analyzed
            diacritical_regex = r"[çćĉċčřŕŗřśŝşšșẋỳŷỹȳāăąēĕėęěīĭįőōĩĕẽã]"
            if re.search(diacritical_regex, word):
                # Add a warning about diacritical marks
                if "warnings" not in analysis:
                    analysis["warnings"] = []
                analysis["warnings"].append(
                    "The original Woccon transcription by John Lawson (1709) does not use diacritical marks. "
                    "The analysis is based on the word with diacritics removed."
                )
                
                # Clean the word for analysis
                clean_word = re.sub(diacritical_regex, "", word)
                
                # Re-run analysis with clean word if different
                if clean_word != word:
                    clean_analysis = original_analyze(clean_word)
                    
                    # Update relevant parts of the analysis
                    for key in ["roots", "affixes", "patterns", "sound_links"]:
                        if key in clean_analysis:
                            analysis[key] = clean_analysis[key]
            
            return analysis
        
        # Replace the analyze_word method
        woccon_t5.analyze_word = enhanced_analyze_word
        
        return woccon_t5

def main():
    """
    Example of how to integrate the OrthographicAccuracyEnhancer with the existing system.
    """
    from woccon_llama_integration import WocconAssistant
    
    # Create and integrate with WocconAssistant
    assistant = WocconAssistant()
    integration = FactualGuardRailIntegration()
    enhanced_assistant = integration.enhance_assistant(assistant)
    
    print("Enhanced WocconAssistant with fact-checking guard rails")
    
    # Test with a query that might trigger hallucination
    response = enhanced_assistant.reply("test_user", "What are the diacritical marks used in Woccon?")
    print(f"Response: {response}")
    
    # You can also enhance other components
    from main import WocconT5
    from woccon_cli import main as cli_main
    
    # Enhance WocconT5
    woccon = WocconT5()
    enhanced_woccon = integration.enhance_woccon_t5(woccon)
    print("Enhanced WocconT5 with hallucination prevention")
    
    # The integration can be applied to any component of the system
    return enhanced_assistant

if __name__ == "__main__":
    main()