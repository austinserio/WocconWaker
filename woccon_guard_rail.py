"""
Woccon Linguistic Fact Checking and Guard Rails System

This system provides validation for claims about the Woccon language
and prevents hallucination of non-existent linguistic features.
"""

import json
import re
from typing import Dict, List, Tuple, Optional, Any

class WocconFactValidator:
    """
    A validator to prevent fabrication of diacritical marks and other linguistic features
    that were not part of the original Woccon documentation by John Lawson.
    """
    
    def __init__(self, dictionary_path: str, rules_path: str):
        """
        Initialize the validator with paths to the dictionary and rules JSON files.
        
        Args:
            dictionary_path: Path to the dictionary JSON file
            rules_path: Path to the rules JSON file
        """
        self.dictionary = self._load_json(dictionary_path)
        self.rules = self._load_json(rules_path)
        
        # Extract attested Woccon words from the dictionary
        self.attested_words = [entry["woccon"] for entry in self.dictionary.get("lexicon", [])]
        
        # Extract the actual orthography used in the documented Woccon words
        self.orthography = self._extract_orthography()
        
        # Initialize linguistic features from the rules file
        self._initialize_linguistic_features()
        
    def _load_json(self, path: str) -> Dict:
        """Load JSON data from a file."""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _extract_orthography(self) -> Dict:
        """Extract the actual orthography used in Woccon documentation."""
        # Get all letters used in Woccon words
        all_letters = set()
        for word in self.attested_words:
            for char in word:
                all_letters.add(char)
        
        # Identify special characters (non-alphanumeric)
        special_chars = {c for c in all_letters if not (c.isalnum() or c.isspace())}
        
        return {
            "alphabet": sorted(list(all_letters)),
            "special_characters": sorted(list(special_chars))
        }
    
    def _initialize_linguistic_features(self):
        """Initialize linguistic features from the rules file."""
        self.phonology = self.rules.get("phonology", {})
        self.morphology = self.rules.get("morphology", {})
        self.syntax = self.rules.get("syntax", {})
        
    def validate_diacritical_claims(self, text: str) -> Dict:
        """
        Validate claims about diacritical marks in Woccon text.
        
        Args:
            text: The text to validate
            
        Returns:
            A dictionary with validation results
        """
        # Check for claims about diacritical marks
        diacritical_patterns = [
            r"cedilla", r"macron", r"breve", r"diacritical mark",
            r"special character", r"accent mark", r"tilde"
        ]
        
        has_diacritical_claims = any(re.search(pattern, text, re.IGNORECASE) for pattern in diacritical_patterns)
        
        if has_diacritical_claims:
            # Check if any attested Woccon words contain diacritical marks
            diacritical_regex = r"[çćĉċčřŕŗřśŝşšșẋỳŷỹȳāăąēĕėęěīĭįőōĩĕẽã]"
            has_diacritical_marks = any(re.search(diacritical_regex, word) for word in self.attested_words)
            
            if not has_diacritical_marks:
                return {
                    "is_valid": False,
                    "correction": "CORRECTION NEEDED: The original Woccon transcription by John Lawson (1709) does not use diacritical marks like cedillas, macrons, or breves. The linguistic notation in modern scholarly work may use IPA symbols, but these are not part of the original orthography. Stick to the actual spelling in the primary source dictionary.",
                    "suggested_response": "The Woccon language as documented by John Lawson in 1709 was written using mostly standard Latin alphabet letters without special diacritical marks. The spelling system used by Lawson to record these words was an attempt to represent the sounds he heard using English orthographic conventions of the early 18th century. Modern linguistic analyses may use IPA and other special symbols, but these weren't part of the original documentation."
                }
        
        return {"is_valid": True}
    
    def validate_phonology_claims(self, text: str) -> Dict:
        """
        Validate claims about Woccon phonology.
        
        Args:
            text: The text to validate
            
        Returns:
            A dictionary with validation results
        """
        # Check for claims about phonology
        phonology_patterns = [
            r"pronuncia", r"sound", r"phonem", r"pronounce", r"vocal", r"consonant"
        ]
        
        has_phonology_claims = any(re.search(pattern, text, re.IGNORECASE) for pattern in phonology_patterns)
        
        if has_phonology_claims:
            # Extract phonological data from rules
            vocalic_phonemes = self.phonology.get("vocalic_phonemes", {})
            consonantal_phonemes = self.phonology.get("consonantal_phonemes", [])
            
            # Create a reference to the actual phonological data
            phonology_facts = {
                "vowels": {
                    "short": vocalic_phonemes.get("short_oral_vowels", []),
                    "long": vocalic_phonemes.get("long_oral_vowels", []),
                    "nasal": vocalic_phonemes.get("nasal_vowels", [])
                },
                "consonants": [c.get("grapheme", "") for c in consonantal_phonemes]
            }
            
            # Check for mismatched phonology claims
            # This is a simplified check - in a real system, use NLP for better detection
            mismatched_phonology = (
                "ç" in text or  # Check for specific fabricated characters
                "cedilla" in text.lower() or 
                re.search(r"soft[a-z\s]+(c|g|n)", text, re.IGNORECASE)
            )
            
            if mismatched_phonology:
                return {
                    "is_valid": False,
                    "correction": "CORRECTION NEEDED: The phonological description doesn't match the documented Woccon sound system. There is no evidence for cedillas or other diacritical marks in the original transcription.",
                    "suggested_response": f"Based on linguistic analysis, Woccon likely had the following sound system:\n\n- Short vowels: {', '.join(phonology_facts['vowels']['short'])}\n- Long vowels: {', '.join(phonology_facts['vowels']['long'])}\n- Nasal vowels: {', '.join(phonology_facts['vowels']['nasal'])}\n- Consonants include: {', '.join(phonology_facts['consonants'])}\n\nIt's important to note that John Lawson's original transcription from 1709 attempted to represent these sounds using English spelling conventions of that time, without special diacritical marks."
                }
        
        return {"is_valid": True}
    
    def validate_woccon_word_spelling(self, text: str) -> Dict:
        """
        Validate the spelling of Woccon words in text.
        
        Args:
            text: The text to validate
            
        Returns:
            A dictionary with validation results
        """
        # Create a case-insensitive lookup for Woccon words
        woccon_dict = {word.lower(): word for word in self.attested_words}
        
        # Extract potential Woccon words (looking for words that are claimed to be Woccon)
        woccon_claim_patterns = [
            r"Woccon word (?:for|is) ['\"]([a-zA-Z\-]+)['\"]",
            r"in Woccon, ['\"]([a-zA-Z\-]+)['\"]",
            r"Woccon term ['\"]([a-zA-Z\-]+)['\"]"
        ]
        
        misspelled_words = []
        
        for pattern in woccon_claim_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                claimed_word = match.group(1).lower()
                
                # Skip common English words that might be part of examples
                if claimed_word in ["the", "and", "for", "is", "of", "to", "in"] or len(claimed_word) <= 2:
                    continue
                
                # Check if this is a valid Woccon word
                if claimed_word not in woccon_dict:
                    # Check if it has a diacritical mark
                    diacritical_regex = r"[çćĉċčřŕŗřśŝşšșẋỳŷỹȳāăąēĕėęěīĭįőōĩĕẽã]"
                    if re.search(diacritical_regex, claimed_word):
                        # Find closest match
                        closest_match = None
                        for word in woccon_dict:
                            # Remove diacritics from claimed word for comparison
                            clean_claimed = re.sub(diacritical_regex, "", claimed_word)
                            if clean_claimed in word or word in clean_claimed:
                                closest_match = woccon_dict[word]
                                break
                        
                        if closest_match:
                            misspelled_words.append({
                                "incorrect": claimed_word, 
                                "correct": closest_match,
                                "has_diacritics": True
                            })
        
        if misspelled_words:
            return {
                "is_valid": False,
                "correction": "CORRECTION NEEDED: Some Woccon words have incorrect diacritical marks added.",
                "suggested_response": "Here are the correct spellings of the Woccon words mentioned:\n\n" + "\n".join([f"- \"{w['incorrect']}\" should be \"{w['correct']}\" (the original Lawson transcription does not use diacritical marks)" for w in misspelled_words]) + "\n\nThese spellings come directly from John Lawson's 1709 documentation."
            }
        
        return {"is_valid": True}
    
    def validate_linguistic_claims(self, text: str) -> Dict:
        """
        Validate various linguistic claims about Woccon.
        
        Args:
            text: The text to validate
            
        Returns:
            A dictionary with validation results
        """
        # Run all validators
        diacritical_validation = self.validate_diacritical_claims(text)
        if not diacritical_validation["is_valid"]:
            return diacritical_validation
        
        phonology_validation = self.validate_phonology_claims(text)
        if not phonology_validation["is_valid"]:
            return phonology_validation
        
        spelling_validation = self.validate_woccon_word_spelling(text)
        if not spelling_validation["is_valid"]:
            return spelling_validation
        
        # Add disclaimer for claims about Woccon grammar or pronunciation
        grammar_pronunciation_claim = re.search(r"(gramm|pronunc|sound)", text, re.IGNORECASE)
        
        if grammar_pronunciation_claim:
            return {
                "is_valid": True,
                "add_disclaimer": True,
                "disclaimer": ""
            }
        
        return {"is_valid": True}
    
    def process_response(self, response_text: str) -> Dict:
        """
        Process a response to ensure accuracy about Woccon linguistics.
        
        Args:
            response_text: The response text to validate
            
        Returns:
            A dictionary with processing results
        """
        # Validate the response
        validation = self.validate_linguistic_claims(response_text)
        
        if not validation.get("is_valid", True):
            # Return a corrected response
            return {
                "needs_correction": True,
                "original_response": response_text,
                "correction": validation.get("correction", ""),
                "suggested_response": validation.get("suggested_response", "")
            }
        
        # Add disclaimer if appropriate
        if validation.get("add_disclaimer", False):
            return {
                "needs_correction": False,
                "enhanced_response": response_text + "\n\n" + validation.get("disclaimer", "")
            }
        
        # Response is good to go
        return {
            "needs_correction": False,
            "enhanced_response": response_text
        }