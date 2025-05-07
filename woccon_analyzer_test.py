#!/usr/bin/env python3
"""
Test script for the enhanced Woccon morphological analyzer.
This script loads the updated rules.json and analyzes a set of known Woccon words
to validate the morphological analyzer's functionality.
"""

import json
import os
import sys
from pprint import pprint

# Add the parent directory to the system path to import the analyzer
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the analyzer
from woccon_morphological_analyzer import WocconMorphologicalAnalyzer

def load_json(path):
    """Load a JSON file"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_analyzer():
    """Run a series of tests on the morphological analyzer"""
    # Load the updated rules
    rules = load_json('woccon_language/rules.json')
    
    # Initialize the analyzer
    analyzer = WocconMorphologicalAnalyzer(rules)
    
    # Test words with known morphological properties
    test_words = [
        {
            "word": "yawowa",
            "meaning": "rain",
            "description": "Contains ya- (water) root and -wa (natural phenomena) suffix"
        },
        {
            "word": "yauh-he",
            "meaning": "Indians",
            "description": "Contains yau- (path) root and -he (animate beings) suffix"
        },
        {
            "word": "wattape",
            "meaning": "gourd/bottle",
            "description": "Contains watta- (container) prefix and -pe (container) suffix"
        },
        {
            "word": "roo-iune",
            "meaning": "blankets",
            "description": "Contains roo- (cloth) root and -iune (manufactured) suffix"
        },
        {
            "word": "wawawa",
            "meaning": "snow",
            "description": "Shows intensive reduplication of wa"
        },
        {
            "word": "kitkilare",
            "meaning": "break in pieces",
            "description": "Shows partial reduplication of kit (break)"
        },
        {
            "word": "kuwã:re",
            "meaning": "he kills it",
            "description": "Contains -re suffix marking independent mode"
        },
        {
            "word": "ni ku:ʔra:de",
            "meaning": "give me something to eat",
            "description": "Contains -de suffix marking imperative mode"
        }
    ]
    
    print("Testing Woccon Morphological Analyzer...")
    print("=" * 80)
    
    # Test each word
    for test in test_words:
        print(f"\nAnalyzing: {test['word']} = '{test['meaning']}'")
        print(f"Expected: {test['description']}")
        
        # Analyze the word
        analysis = analyzer.analyze_word(test['word'], test['meaning'])
        
        # Print results
        print("Analysis results:")
        
        # Print roots
        if analysis['roots']:
            print("  Roots:")
            for root in analysis['roots']:
                if root['confidence'] != 'low':
                    print(f"    - {root['root']} = '{root['meaning']}' ({root['confidence']} confidence)")
        
        # Print affixes
        if analysis['affixes']:
            print("  Affixes:")
            for affix in analysis['affixes']:
                print(f"    - {affix['type']} {affix['form']} = {affix['function']}")
        
        # Print reduplication
        if analysis['reduplication']:
            print("  Reduplication:")
            red = analysis['reduplication']
            print(f"    - {red['type']} ({red['pattern']}): {red['description']}")
        
        # Print inflectional mode
        if analysis['inflectional_mode'] and analysis['inflectional_mode']['mode'] != 'unknown':
            mode = analysis['inflectional_mode']
            print(f"  Inflectional Mode: {mode['mode']} (marked by {mode['marker']})")
            print(f"    - {mode['description']}")
        
        # Print syllable structure
        if analysis['syllable_structure']:
            print(f"  Syllable Structure: {'-'.join(analysis['syllable_structure'])}")
        
        print("-" * 40)
    
    # Test additional analyzer functions
    print("\nTesting specific analyzer functions:")
    print("=" * 80)
    
    # Test reduplication detection
    print("\nTesting reduplication detection:")
    for word in ["wawawa", "kitkilare", "sapĩ pẽ:ʔpẽ:ʔ"]:
        red = analyzer.detect_reduplication(word)
        if red:
            print(f"  {word}: {red['type']} ({red['pattern']}) - {red['description']}")
        else:
            print(f"  {word}: No reduplication detected")
    
    # Test inflectional mode identification
    print("\nTesting inflectional mode identification:")
    for word in ["kuwã:re", "ĩkta:ʔ", "ni ku:ʔra:de", "katẽ:ne"]:
        mode = analyzer.identify_inflectional_mode(word)
        if mode['mode'] != 'unknown':
            print(f"  {word}: {mode['mode']} mode (marked by {mode['marker']})")
        else:
            print(f"  {word}: No inflectional mode identified")
    
    print("\nTesting complete!")

if __name__ == "__main__":
    test_analyzer()