"""
Modified evaluation script focused on existing Woccon word analysis rather than generation.
This script generates prompts for word analysis and lookup, tests them against the model,
and evaluates the quality of the responses.
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
        if prompt_type == "word_lookup":
            return self.prompt_generator.word_lookup_prompt(kwargs.get("search_term", "yau"))
        elif prompt_type == "word_analysis":
            return self.prompt_generator.word_analysis_prompt(kwargs.get("woccon_word", "yawowa"))
        elif prompt_type == "category_browse":
            return self.prompt_generator.category_browse_prompt(kwargs.get("category", "animals"))
        elif prompt_type == "sound_correspondence":
            return self.prompt_generator.sound_correspondence_prompt(kwargs.get("catawba_word", "tasi"))
        elif prompt_type == "language_info":
            return self.prompt_generator.language_info_prompt()
        else:
            raise ValueError(f"Unknown prompt type: {prompt_type}")
            
    def query_model(self, prompt: str, max_length: int = 256) -> str:
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
        
    def evaluate_word_analysis(self, woccon_word: str, response: str) -> Dict[str, Any]:
        """Evaluate the quality of a word analysis response"""
        # Look up the correct information about this word
        word_info = None
        for word in self.dictionary.get("lexicon", []):
            if word["woccon"].lower() == woccon_word.lower():
                word_info = word
                break
                
        if not word_info:
            return {"error": f"Word {woccon_word} not found in dictionary"}
            
        # Find correct roots
        correct_roots = []
        for root_name, root_info in self.roots.items():
            root_clean = root_name.rstrip('-')
            if word_info["woccon"].lower().startswith(root_clean):
                correct_roots.append(root_name)
                
        # Find correct suffixes
        correct_suffixes = []
        known_suffixes = ["-wa", "-he", "-iune", "-pe"]
        for suffix in known_suffixes:
            clean_suffix = suffix.lstrip("-")
            if word_info["woccon"].lower().endswith(clean_suffix):
                correct_suffixes.append(suffix)
                
        # Check if the response contains the correct information
        response_lower = response.lower()
        
        # Check for meaning
        has_correct_meaning = word_info["english"].lower() in response_lower
        
        # Check for roots
        root_mentions = []
        for root in correct_roots:
            if root.lower() in response_lower:
                root_mentions.append(root)
                
        # Check for suffixes
        suffix_mentions = []
        for suffix in correct_suffixes:
            if suffix.lower() in response_lower:
                suffix_mentions.append(suffix)
                
        # Evaluate completeness and accuracy
        completeness = 0.0
        if has_correct_meaning:
            completeness += 0.3
            
        if len(root_mentions) > 0:
            completeness += 0.4 * (len(root_mentions) / max(1, len(correct_roots)))
            
        if len(suffix_mentions) > 0:
            completeness += 0.3 * (len(suffix_mentions) / max(1, len(correct_suffixes)))
            
        # Check for linguistic depth
        depth_markers = [
            "morpholog", "structur", "analys", "root", "suffix", "prefix", 
            "affix", "compound", "phonolog", "sound", "pattern"
        ]
        
        depth_score = sum(1 for marker in depth_markers if marker in response_lower) / len(depth_markers)
        
        # Overall quality rating
        if completeness >= 0.7 and depth_score >= 0.5:
            quality = "high"
        elif completeness >= 0.4 and depth_score >= 0.3:
            quality = "medium"
        else:
            quality = "low"
            
        evaluation = {
            "word": woccon_word,
            "meaning": word_info["english"],
            "has_correct_meaning": has_correct_meaning,
            "correct_roots": correct_roots,
            "found_roots": root_mentions,
            "correct_suffixes": correct_suffixes,
            "found_suffixes": suffix_mentions,
            "linguistic_depth": depth_score,
            "completeness": completeness,
            "overall_quality": quality
        }
        
        return evaluation
        
    def evaluate_word_lookup(self, search_term: str, response: str) -> Dict[str, Any]:
        """Evaluate the quality of a word lookup response"""
        # Find the correct matches for this search term
        correct_matches = []
        
        # Check if it's a Woccon word first
        exact_match = None
        for word in self.dictionary.get("lexicon", []):
            if word["woccon"].lower() == search_term.lower():
                exact_match = word
                correct_matches.append(word)
                break
                
        # If not an exact Woccon match, look for English matches
        if not exact_match:
            for word in self.dictionary.get("lexicon", []):
                if search_term.lower() in word["english"].lower():
                    correct_matches.append(word)
                    
        # Check if the response contains the correct matches
        response_lower = response.lower()
        
        found_matches = []
        for match in correct_matches:
            # Check for both the Woccon word and English meaning
            if match["woccon"].lower() in response_lower and match["english"].lower() in response_lower:
                found_matches.append(match)
                
        # Calculate coverage
        coverage = len(found_matches) / max(1, len(correct_matches))
        
        # Check for part of speech and additional context
        detail_score = 0.0
        detail_markers = ["part of speech", "pos", "noun", "verb", "adjective", "adverb"]
        
        for marker in detail_markers:
            if marker in response_lower:
                detail_score += 1.0 / len(detail_markers)
                break
                
        # Overall quality rating
        if coverage >= 0.7 and detail_score >= 0.5:
            quality = "high"
        elif coverage >= 0.4 and detail_score >= 0.3:
            quality = "medium"
        else:
            quality = "low"
            
        evaluation = {
            "search_term": search_term,
            "correct_matches": len(correct_matches),
            "found_matches": len(found_matches),
            "coverage": coverage,
            "includes_details": detail_score,
            "overall_quality": quality
        }
        
        return evaluation
        
    def evaluate_category_browse(self, category: str, response: str) -> Dict[str, Any]:
        """Evaluate the quality of a category browse response"""
        # Define keywords for each category
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
            return {"error": f"Category {category} not recognized"}
            
        # Find correct matches for this category
        correct_matches = []
        for word in self.dictionary.get("lexicon", []):
            eng = word["english"].lower()
            if any(keyword in eng for keyword in keywords):
                correct_matches.append(word)
                
        # Check if the response contains the correct matches
        response_lower = response.lower()
        
        found_matches = []
        for match in correct_matches:
            # Check for both the Woccon word and English meaning
            if match["woccon"].lower() in response_lower and match["english"].lower() in response_lower:
                found_matches.append(match)
                
        # Calculate coverage
        coverage = len(found_matches) / max(1, len(correct_matches))
        
        # Check for organization and formatting
        organization_score = 0.0
        organization_markers = ["category", "list", "found", "words", "summary"]
        
        for marker in organization_markers:
            if marker in response_lower:
                organization_score += 1.0 / len(organization_markers)
                
        # Overall quality rating
        if coverage >= 0.7 and organization_score >= 0.5:
            quality = "high"
        elif coverage >= 0.4 and organization_score >= 0.3:
            quality = "medium"
        else:
            quality = "low"
            
        evaluation = {
            "category": category,
            "normalized_category": norm_category,
            "correct_matches": len(correct_matches),
            "found_matches": len(found_matches),
            "coverage": coverage,
            "organization": organization_score,
            "overall_quality": quality
        }
        
        return evaluation
    
    def evaluate_sound_correspondence(self, catawba_word: str, response: str) -> Dict[str, Any]:
        """Evaluate the quality of a sound correspondence analysis"""
        # Get sound correspondences from rules
        correspondences = self.dictionary.get("sound_correspondences", {}).get("woccon_to_catawba", [])
        
        # Check if the response mentions the sound correspondences
        response_lower = response.lower()
        
        mentioned_correspondences = []
        for corr in correspondences:
            if f"{corr['catawba']}" in response_lower and f"{corr['woccon']}" in response_lower:
                mentioned_correspondences.append(corr)
                
        # Calculate coverage
        coverage = len(mentioned_correspondences) / max(1, len(correspondences))
        
        # Check for linguistic analysis
        analysis_score = 0.0
        analysis_markers = ["correspond", "sound change", "phonolog", "historical", "language", "pattern"]
        
        for marker in analysis_markers:
            if marker in response_lower:
                analysis_score += 1.0 / len(analysis_markers)
                
        # Overall quality rating
        if coverage >= 0.3 and analysis_score >= 0.5:  # Lower threshold since not all correspondences are relevant
            quality = "high"
        elif coverage >= 0.2 and analysis_score >= 0.3:
            quality = "medium"
        else:
            quality = "low"
            
        evaluation = {
            "catawba_word": catawba_word,
            "total_correspondences": len(correspondences),
            "mentioned_correspondences": len(mentioned_correspondences),
            "coverage": coverage,
            "linguistic_analysis": analysis_score,
            "overall_quality": quality
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
            if prompt_type == "word_lookup":
                evaluation = self.evaluate_word_lookup(test_case["search_term"], response)
            elif prompt_type == "word_analysis":
                evaluation = self.evaluate_word_analysis(test_case["woccon_word"], response)
            elif prompt_type == "category_browse":
                evaluation = self.evaluate_category_browse(test_case["category"], response)
            elif prompt_type == "sound_correspondence":
                evaluation = self.evaluate_sound_correspondence(test_case["catawba_word"], response)
            
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
            "word_lookup": [
                {"search_term": "yau"},
                {"search_term": "fire"},
                {"search_term": "dog"}
            ],
            "word_analysis": [
                {"woccon_word": "yawowa"},
                {"woccon_word": "tauh-he"},
                {"woccon_word": "wattape"}
            ],
            "category_browse": [
                {"category": "animals"},
                {"category": "tools"},
                {"category": "clothing"}
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
                report += f"Response: {result['response'][:150]}...\n"
                
                # Format evaluation details
                eval_info = result['evaluation']
                report += "Evaluation:\n"
                
                if prompt_type == "word_lookup":
                    report += f"  Correct Matches: {eval_info.get('correct_matches', 0)}\n"
                    report += f"  Found Matches: {eval_info.get('found_matches', 0)}\n"
                    report += f"  Coverage: {eval_info.get('coverage', 0):.2f}\n"
                    report += f"  Includes Details: {eval_info.get('includes_details', 0):.2f}\n"
                    report += f"  Overall Quality: {eval_info.get('overall_quality', 'unknown')}\n"
                    
                elif prompt_type == "word_analysis":
                    report += f"  Has Correct Meaning: {eval_info.get('has_correct_meaning', False)}\n"
                    report += f"  Correct Roots: {', '.join(eval_info.get('correct_roots', []))}\n"
                    report += f"  Found Roots: {', '.join(eval_info.get('found_roots', []))}\n"
                    report += f"  Correct Suffixes: {', '.join(eval_info.get('correct_suffixes', []))}\n"
                    report += f"  Found Suffixes: {', '.join(eval_info.get('found_suffixes', []))}\n"
                    report += f"  Linguistic Depth: {eval_info.get('linguistic_depth', 0):.2f}\n"
                    report += f"  Completeness: {eval_info.get('completeness', 0):.2f}\n"
                    report += f"  Overall Quality: {eval_info.get('overall_quality', 'unknown')}\n"
                
                elif prompt_type == "category_browse":
                    report += f"  Category: {eval_info.get('category', '')}\n"
                    report += f"  Correct Matches: {eval_info.get('correct_matches', 0)}\n"
                    report += f"  Found Matches: {eval_info.get('found_matches', 0)}\n"
                    report += f"  Coverage: {eval_info.get('coverage', 0):.2f}\n"
                    report += f"  Organization: {eval_info.get('organization', 0):.2f}\n"
                    report += f"  Overall Quality: {eval_info.get('overall_quality', 'unknown')}\n"
                
                elif prompt_type == "sound_correspondence":
                    report += f"  Catawba Word: {eval_info.get('catawba_word', '')}\n"
                    report += f"  Total Correspondences: {eval_info.get('total_correspondences', 0)}\n"
                    report += f"  Mentioned Correspondences: {eval_info.get('mentioned_correspondences', 0)}\n"
                    report += f"  Coverage: {eval_info.get('coverage', 0):.2f}\n"
                    report += f"  Linguistic Analysis: {eval_info.get('linguistic_analysis', 0):.2f}\n"
                    report += f"  Overall Quality: {eval_info.get('overall_quality', 'unknown')}\n"
                
                report += "\n" + "-"*50 + "\n\n"
            
        return report

def run_simple_test():
    """Run a simple test with just one or two examples"""
    evaluator = WocconEvaluator()
    
    print("\n=== RUNNING SIMPLE MODEL TEST ===")
    
    # Test word analysis prompt
    test_prompt = evaluator.generate_prompt(
        "word_analysis", 
        woccon_word="yawowa"
    )
    print("Test prompt:")
    print(test_prompt)
    
    print("\nGenerating response (this may take a moment)...")
    response = evaluator.query_model(test_prompt)
    
    print("\nModel response:")
    print(response)
    
    print("\nEvaluating response...")
    evaluation = evaluator.evaluate_word_analysis("yawowa", response)
    
    print("Evaluation results:")
    print(f"Has correct meaning: {evaluation['has_correct_meaning']}")
    print(f"Found roots: {evaluation['found_roots']}")
    print(f"Found suffixes: {evaluation['found_suffixes']}")
    print(f"Linguistic depth: {evaluation['linguistic_depth']:.2f}")
    print(f"Completeness: {evaluation['completeness']:.2f}")
    print(f"Overall quality: {evaluation['overall_quality']}")
    
    # Also test a word lookup
    print("\n--- Testing Word Lookup ---")
    lookup_prompt = evaluator.generate_prompt(
        "word_lookup", 
        search_term="fire"
    )
    lookup_response = evaluator.query_model(lookup_prompt)
    lookup_eval = evaluator.evaluate_word_lookup("fire", lookup_response)
    
    print("Word lookup evaluation:")
    print(f"Coverage: {lookup_eval['coverage']:.2f}")
    print(f"Overall quality: {lookup_eval['overall_quality']}")
    
    return {
        "word_analysis": {"prompt": test_prompt, "response": response, "evaluation": evaluation},
        "word_lookup": {"prompt": lookup_prompt, "response": lookup_response, "evaluation": lookup_eval}
    }

# Example usage
if __name__ == "__main__":
    evaluator = WocconEvaluator()
    
    # Generate a few example prompts
    word_lookup_prompt = evaluator.generate_prompt(
        "word_lookup", 
        search_term="fire"
    )
    
    word_analysis_prompt = evaluator.generate_prompt(
        "word_analysis",
        woccon_word="yawowa"
    )
    
    print("=== EXAMPLE PROMPTS ===\n")
    print("Word Lookup Prompt:")
    print(word_lookup_prompt)
    print("\nWord Analysis Prompt:")
    print(word_analysis_prompt)
    
    # Uncomment to run a simple test
    # test_result = run_simple_test()
    
    print("\n=== NOTE ON EVALUATION ===")
    print("Full evaluation requires running the model, which may take time.")
    print("To run a complete evaluation suite, uncomment the code below:")
    print("""
    # Run complete evaluation
    results = evaluator.run_evaluation_suite()
    report = evaluator.format_results(results)
    print(report)
    """)
    
    # Alternatively, to run a simple test:
    print("""
    # Run a simple test
    test_result = run_simple_test()
    """)
    test_result = run_simple_test()

        