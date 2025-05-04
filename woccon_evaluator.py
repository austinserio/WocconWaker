"""
Evaluation script for testing T5 model responses to Woccon prompts.
This script generates prompts, submits them to the model, and evaluates the responses
based on linguistic rules from the Woccon language.
"""

import json
import re
import random
from typing import Dict, List, Tuple, Optional, Any
from transformers import T5ForConditionalGeneration, AutoTokenizer
import torch
from woccon_prompt_templates import WocconPromptGenerator

class WocconEvaluator:
    def __init__(self, 
                 model_name: str = "google/byt5-base", 
                 dictionary_path: str = "woccon_language/dictionary.json",
                 rules_path: str = "woccon_language/rules.json"):
        """Initialize the evaluator with model and data"""
        # Load the model and tokenizer
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = T5ForConditionalGeneration.from_pretrained(model_name)
        
        # Initialize prompt generator
        self.prompt_generator = WocconPromptGenerator(dictionary_path, rules_path)
        
        # Load dictionary and rules for evaluation
        with open(dictionary_path, 'r', encoding='utf-8') as f:
            self.dictionary = json.load(f)
            
        with open(rules_path, 'r', encoding='utf-8') as f:
            self.rules = json.load(f)
            
        # Extract linguistic patterns for evaluation
        self.roots = {entry["root"]: entry for entry in self.dictionary.get("common_roots", [])}
        self.phonology = self._extract_phonology()
        
    def _extract_phonology(self) -> Dict[str, Any]:
        """Extract phonological information from rules"""
        return self.rules.get("phonology", {})
        
    def generate_prompt(self, prompt_type: str, **kwargs) -> str:
        """Generate a prompt of the specified type"""
        if prompt_type == "translation":
            return self.prompt_generator.translate_prompt(kwargs.get("english_text", "The dog is running"))
        elif prompt_type == "word_analysis":
            return self.prompt_generator.word_analysis_prompt(kwargs.get("woccon_word", "yawowa"))
        elif prompt_type == "word_generation":
            return self.prompt_generator.word_generation_prompt(
                kwargs.get("meaning", "river"), 
                root=kwargs.get("root")
            )
        elif prompt_type == "sound_correspondence":
            return self.prompt_generator.sound_correspondence_prompt(kwargs.get("catawba_word", "tasi"))
        elif prompt_type == "sentence_structure":
            return self.prompt_generator.sentence_structure_prompt(kwargs.get("english_sentence", "The dog sees the fire"))
        else:
            raise ValueError(f"Unknown prompt type: {prompt_type}")
            
    def query_model(self, prompt: str, max_length: int = 100) -> str:
        """Submit a prompt to the T5 model and get the response"""
        input_ids = self.tokenizer(prompt, return_tensors="pt").input_ids
        
        # Generate output from the model
        output_ids = self.model.generate(
            input_ids, 
            max_length=max_length,
            do_sample=True,
            top_p=0.9,
            temperature=0.7
        )
        
        response = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
        return response
        
    def evaluate_phonology(self, woccon_word: str) -> Dict[str, Any]:
        """Evaluate if a generated word follows Woccon phonological patterns"""
        # Define regular expressions for valid consonant and vowel patterns
        valid_consonants = r'[ptkmnrshwy]'
        valid_vowels = r'[aeiou]'
        
        # Check if the word contains only valid phonemes
        invalid_chars = re.sub(f'{valid_consonants}|{valid_vowels}|-', '', woccon_word.lower())
        
        # Check syllable structure (approximate CV, CVC patterns)
        syllable_pattern = re.compile(f'({valid_consonants}?{valid_vowels}+{valid_consonants}*)')
        syllables = syllable_pattern.findall(woccon_word.lower())
        
        evaluation = {
            "follows_phonology": len(invalid_chars) == 0,
            "invalid_characters": list(invalid_chars) if invalid_chars else None,
            "approximate_syllables": syllables,
            "syllable_count": len(syllables)
        }
        
        return evaluation
        
    def evaluate_morphology(self, woccon_word: str, meaning: str = None) -> Dict[str, Any]:
        """Evaluate if a generated word follows Woccon morphological patterns"""
        # Check for known roots
        found_roots = []
        for root_name, root_info in self.roots.items():
            clean_root = root_name.rstrip('-')
            if clean_root in woccon_word.lower():
                root_match = {
                    "root": root_name,
                    "meaning": root_info["meaning"],
                    "position": woccon_word.lower().find(clean_root)
                }
                
                # Check if the meaning matches (if provided)
                if meaning:
                    semantic_match = any(term in meaning.lower() for term in root_info["meaning"].lower().split(", "))
                    root_match["semantic_match"] = semantic_match
                    
                found_roots.append(root_match)
                
        # Check for known affixes
        known_suffixes = ["-wa", "-he", "-iune", "-pe"]
        found_suffixes = []
        
        for suffix in known_suffixes:
            clean_suffix = suffix.lstrip("-")
            if woccon_word.lower().endswith(clean_suffix):
                found_suffixes.append(suffix)
                
        evaluation = {
            "found_roots": found_roots,
            "found_suffixes": found_suffixes,
            "has_recognizable_structure": len(found_roots) > 0 or len(found_suffixes) > 0
        }
        
        return evaluation
        
    def evaluate_translation(self, english: str, woccon: str) -> Dict[str, Any]:
        """Evaluate a translation from English to Woccon"""
        # Look for words we know should be in the translation
        expected_words = []
        found_words = []
        
        # Extract key content words from English
        content_words = [word.lower() for word in english.split() if len(word) > 3]
        
        # Find dictionary entries that might match these content words
        for word in content_words:
            for entry in self.dictionary.get("lexicon", []):
                if word in entry["english"].lower():
                    expected_words.append({
                        "english": word,
                        "woccon": entry["woccon"]
                    })
                    
                    # Check if this word appears in the translation
                    if entry["woccon"].lower() in woccon.lower():
                        found_words.append(entry["woccon"])
        
        # Evaluate phonology
        phonology_evaluation = self.evaluate_phonology(woccon)
        
        # Combine evaluations
        evaluation = {
            "expected_words": expected_words,
            "found_words": found_words,
            "word_coverage": len(found_words) / len(expected_words) if expected_words else 0,
            "phonology": phonology_evaluation,
            "overall_quality": "high" if phonology_evaluation["follows_phonology"] and (len(found_words) / max(1, len(expected_words)) > 0.5) else "medium" if phonology_evaluation["follows_phonology"] else "low"
        }
        
        return evaluation
        
    def batch_evaluate(self, prompt_type: str, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run a batch of test cases and evaluate results"""
        results = []
        
        for test_case in test_cases:
            # Generate prompt
            prompt = self.generate_prompt(prompt_type, **test_case)
            
            # Get model response
            response = self.query_model(prompt)
            
            # Evaluate based on prompt type
            evaluation = {}
            if prompt_type == "translation":
                evaluation = self.evaluate_translation(test_case["english_text"], response)
            elif prompt_type == "word_generation":
                evaluation = {
                    "phonology": self.evaluate_phonology(response),
                    "morphology": self.evaluate_morphology(response, test_case.get("meaning"))
                }
            
            # Store result
            result = {
                "test_case": test_case,
                "prompt": prompt,
                "response": response,
                "evaluation": evaluation
            }
            
            results.append(result)
            
        return results
        
    def run_evaluation_suite(self) -> Dict[str, List[Dict[str, Any]]]:
        """Run a comprehensive evaluation suite across different prompt types"""
        # Define test cases for each prompt type
        test_suites = {
            "translation": [
                {"english_text": "The dog is black"},
                {"english_text": "I see a fire"},
                {"english_text": "The rain is falling"}
            ],
            "word_generation": [
                {"meaning": "river", "root": "ya-"},
                {"meaning": "shirt", "root": "roo-"},
                {"meaning": "forest", "root": "yon-"}
            ]
        }
        
        # Run evaluations
        results = {}
        for prompt_type, test_cases in test_suites.items():
            results[prompt_type] = self.batch_evaluate(prompt_type, test_cases)
            
        return results
        
    def format_results(self, results: Dict[str, List[Dict[str, Any]]]) -> str:
        """Format evaluation results as a readable report"""
        report = "=== WOCCON MODEL EVALUATION REPORT ===\n\n"
        
        for prompt_type, test_results in results.items():
            report += f"--- {prompt_type.upper()} EVALUATIONS ---\n\n"
            
            for i, result in enumerate(test_results):
                report += f"Test Case {i+1}: {result['test_case']}\n"
                report += f"Prompt: {result['prompt'][:100]}...\n"
                report += f"Response: {result['response']}\n"
                
                # Format evaluation details
                eval_info = result['evaluation']
                report += "Evaluation:\n"
                
                if prompt_type == "translation":
                    report += f"  Word Coverage: {eval_info['word_coverage']:.2f}\n"
                    report += f"  Expected Words: {', '.join([w['woccon'] for w in eval_info['expected_words']])}\n"
                    report += f"  Found Words: {', '.join(eval_info['found_words'])}\n"
                    report += f"  Follows Phonology: {eval_info['phonology']['follows_phonology']}\n"
                    report += f"  Overall Quality: {eval_info['overall_quality']}\n"
                    
                elif prompt_type == "word_generation":
                    report += f"  Follows Phonology: {eval_info['phonology']['follows_phonology']}\n"
                    report += f"  Syllable Count: {eval_info['phonology']['syllable_count']}\n"
                    
                    morphology = eval_info['morphology']
                    report += f"  Found Roots: {len(morphology['found_roots'])}\n"
                    for root in morphology.get('found_roots', []):
                        report += f"    {root['root']} = {root['meaning']}\n"
                        
                    report += f"  Found Suffixes: {', '.join(morphology['found_suffixes'])}\n"
                    report += f"  Has Recognizable Structure: {morphology['has_recognizable_structure']}\n"
                
                report += "\n" + "-"*50 + "\n\n"
            
        return report


# Add this at the end of the file before the if __name__ == "__main__" block
def run_simple_test():
    """Run a simple test with just one or two examples"""
    evaluator = WocconEvaluator()
    
    print("\n=== RUNNING SIMPLE MODEL TEST ===")
    
    # Test a single translation prompt
    test_prompt = evaluator.generate_prompt(
        "translation", 
        english_text="The dog is black"
    )
    print("Test prompt:")
    print(test_prompt)
    
    print("\nGenerating response (this may take a moment)...")
    response = evaluator.query_model(test_prompt)
    
    print("\nModel response:")
    print(response)
    
    print("\nEvaluating response...")
    evaluation = evaluator.evaluate_translation("The dog is black", response)
    
    print("Evaluation results:")
    print(f"Word coverage: {evaluation['word_coverage']:.2f}")
    print(f"Follows phonology: {evaluation['phonology']['follows_phonology']}")
    print(f"Overall quality: {evaluation['overall_quality']}")
    
    return {"prompt": test_prompt, "response": response, "evaluation": evaluation}

# Example usage
if __name__ == "__main__":
    evaluator = WocconEvaluator()
    
    # Generate a few example prompts
    translation_prompt = evaluator.generate_prompt(
        "translation", 
        english_text="The dog is running"
    )
    
    word_generation_prompt = evaluator.generate_prompt(
        "word_generation",
        meaning="river",
        root="ya-"
    )
    


    print("=== EXAMPLE PROMPTS ===\n")
    print("Translation Prompt:")
    print(translation_prompt)
    print("\nWord Generation Prompt:")
    print(word_generation_prompt)
    
    print("\n=== NOTE ON EVALUATION ===")
    print("Full evaluation requires running the model, which may take time.")
    print("To run a complete evaluation suite, uncomment the code below:")
    print("""
    # Run complete evaluation
    results = evaluator.run_evaluation_suite()
    report = evaluator.format_results(results)
    print(report)
    """)

        # Uncomment to run a simple test
    test_result = run_simple_test()