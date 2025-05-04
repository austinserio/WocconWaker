#!/usr/bin/env python3
"""
Command-line interface for testing WocconT5 functionality.
This script allows you to interact with the WocconT5 class directly from the terminal.
"""

import sys
import json
import argparse
from typing import Dict, List, Optional

# Import your WocconT5 class
from main import WocconT5

def print_help():
    """Print help information about available commands"""
    print("\nWoccon Language CLI - Available Commands:")
    print("==========================================")
    print("lookup <word>      - Look up a word in English or Woccon")
    print("analyze <word>     - Analyze the structure of a Woccon word")
    print("category <cat>     - Browse words in a specific category")
    print("roots              - List all known Woccon roots")
    print("affixes            - List all known Woccon affixes")
    print("info               - Show information about the Woccon language")
    print("help               - Show this help information")
    print("quit               - Exit the program")
    print("\nExample: analyze yawowa")
    print("==========================================\n")

def format_word_entry(entry: Dict) -> str:
    """Format a dictionary entry for display"""
    output = f"{entry['woccon']} = {entry['english']} ({entry['pos']})"
    return output

def lookup_word(woccon: WocconT5, term: str) -> str:
    """Look up a word in both directions (English to Woccon and Woccon to English)"""
    result = []
    
    # First try Woccon to English
    entry = woccon.lookup_word(term, "woc_to_eng")
    if entry:
        result.append(f"\nWoccon to English:")
        result.append(f"  {format_word_entry(entry)}")
    
    # Then try English to Woccon
    entries = []
    for word in woccon.dictionary.get("lexicon", []):
        if term.lower() in word["english"].lower():
            entries.append(word)
    
    if entries:
        result.append(f"\nEnglish to Woccon:")
        for entry in entries:
            result.append(f"  {format_word_entry(entry)}")
    
    if not result:
        return f"No matches found for '{term}'"
    
    return "\n".join(result)

def analyze_word(woccon: WocconT5, word: str) -> str:
    """Analyze the structure of a Woccon word"""
    # First check if the word exists
    entry = woccon.lookup_word(word, "woc_to_eng")
    if not entry:
        return f"Word '{word}' not found in the Woccon dictionary."
    
    # Get full analysis
    analysis = woccon.analyze_word(word)
    
    # Format the output
    result = []
    result.append(f"Analysis of '{word}':")
    result.append(f"Meaning: {entry['english']}")
    result.append(f"Part of speech: {entry['pos']}\n")
    
    # Show affixes
    if analysis["affixes"]:
        result.append("Affixes Found:")
        for affix in sorted(analysis["affixes"], key=lambda x: x["position"]):
            confidence = affix.get('confidence', 'medium')
            result.append(f"- {affix['type'].capitalize()} '{affix['form']}' = {affix['function']} ({confidence} confidence)")
            if affix.get("semantic_type"):
                result.append(f"  Type: {affix['semantic_type'].replace('_', ' ').title()}")
            if affix.get("examples"):
                result.append("  Examples:")
                for ex in affix["examples"]:
                    result.append(f"  - {ex}")
        result.append("")  # Empty line
    
    # Show roots
    if analysis["roots"]:
        result.append("Roots Found:")
        for root_info in analysis["roots"]:
            confidence = f"{root_info['match_type']} ({root_info['confidence']} confidence)"
            result.append(f"- Found {confidence} '{root_info['root']}' meaning '{root_info['meaning']}'")
            if root_info.get("note"):
                result.append(f"  Note: {root_info['note']}")
            if root_info["derivatives"]:
                result.append("  Known derivatives:")
                for deriv in root_info["derivatives"]:
                    result.append(f"  - {deriv}")
        result.append("")
    
    # Show sound correspondences
    if analysis["sound_links"]:
        result.append("Sound Correspondences:")
        for link in sorted(analysis["sound_links"], key=lambda x: x.get("position", 0)):
            result.append(f"- Woccon '{link['woccon']}' corresponds to Catawba '{link['catawba']}'")
            if link.get("examples"):
                result.append("  Examples:")
                for ex in link["examples"]:
                    result.append(f"  - {ex}")
        result.append("")
    
    # Show semantic groups
    if analysis["semantic_groups"]:
        result.append("Semantic Groups:")
        for group_name, words in sorted(analysis["semantic_groups"].items()):
            if words:  # Only show non-empty groups
                result.append(f"\n{group_name.replace('_', ' ').title()}:")
                for word in sorted(words, key=lambda x: x["english"]):
                    result.append(f"- {word['woccon']} = {word['english']}")
    
    return "\n".join(result)

def browse_category(woccon: WocconT5, category: str) -> str:
    """Browse words in a specific semantic category"""
    # Define category keywords
    categories = {
        "animals": ["fish", "snake", "bird", "dog", "wolf", "squirrel", "panther"],
        "water": ["water", "rain", "fish", "river", "stream", "wet"],
        "clothing": ["cloth", "blanket", "shirt", "wear", "breech", "stocking", "hide", "skin", "buckskin"],
        "containers": ["container", "bottle", "bowl", "basket", "box", "gourd"],
        "body_parts": ["head", "hand", "body", "foot", "hair", "face"],
        "natural_elements": ["tree", "wood", "fire", "stone", "rock", "earth"],
        "tools": ["tool", "knife", "axe", "spoon", "hoe", "needle", "gunpowder", "weapon"],
        "cultural_terms": ["indian", "chief", "warrior", "spirit", "ceremony", "hominy", "skin", "hide", "buckskin"]
    }
    
    # Normalize category
    norm_category = category.lower()
    
    # Handle common aliases
    if norm_category in ["animal", "creature"]:
        norm_category = "animals"
    elif norm_category in ["water_related", "rain"]:
        norm_category = "water"
    elif norm_category in ["clothes", "garment"]:
        norm_category = "clothing"
    elif norm_category in ["container", "vessel"]:
        norm_category = "containers"
    elif norm_category in ["body", "body_part"]:
        norm_category = "body_parts"
    elif norm_category in ["nature", "element"]:
        norm_category = "natural_elements"
    elif norm_category in ["tool", "weapon", "implement"]:
        norm_category = "tools"
    elif norm_category in ["cultural", "ceremony", "culture"]:
        norm_category = "cultural_terms"
    
    # Check if category exists
    if norm_category not in categories:
        avail_cats = ", ".join(categories.keys())
        return f"Category '{category}' not found. Available categories: {avail_cats}"
    
    # Get keywords for this category
    keywords = categories[norm_category]
    
    # Find matching words
    matches = []
    for word in woccon.dictionary.get("lexicon", []):
        if any(keyword in word["english"].lower() for keyword in keywords):
            matches.append(word)
    
    if not matches:
        return f"No words found in category '{norm_category}'"
    
    # Format output
    result = []
    result.append(f"Words in category '{norm_category}':")
    for word in sorted(matches, key=lambda x: x["woccon"]):
        result.append(f"- {format_word_entry(word)}")
    
    result.append(f"\nFound {len(matches)} words in this category.")
    
    return "\n".join(result)

def list_roots(woccon: WocconT5) -> str:
    """List all known Woccon roots"""
    roots = woccon.dictionary.get("common_roots", [])
    
    if not roots:
        return "No root information available."
    
    result = []
    result.append("Known Woccon Roots:")
    
    for root in roots:
        result.append(f"\n{root['root']} = {root['meaning']}")
        if "derivatives" in root and root["derivatives"]:
            result.append("  Derivatives:")
            for deriv in root["derivatives"]:
                result.append(f"  - {deriv}")
    
    return "\n".join(result)

def list_affixes(woccon: WocconT5) -> str:
    """List all known Woccon affixes"""
    # We'll extract affixes from our word analysis logic
    result = []
    result.append("Known Woccon Affixes:")
    
    # Known suffix patterns
    suffix_patterns = [
        {
            "form": "-wa",
            "function": "indicates natural phenomena or repeated actions",
            "examples": ["wawawa (snow)", "yawowa (rain)"],
            "type": "natural_phenomena"
        },
        {
            "form": "-he",
            "function": "nominal suffix, often in terms for animate beings",
            "examples": ["yauh-he (Indians)", "tauh-he (dog)"],
            "type": "animate_beings"
        },
        {
            "form": "-iune",
            "function": "indicates manufactured or processed items",
            "examples": ["roo-iune (blankets)"],
            "type": "artifacts"
        },
        {
            "form": "-pe",
            "function": "indicates containers or vessels",
            "examples": ["wattape (gourd/bottle)"],
            "type": "containers"
        }
    ]
    
    # Known prefix patterns
    prefix_patterns = [
        {
            "form": "watta-",
            "function": "container prefix",
            "examples": ["wattape (gourd/bottle)", "wattapi (star vessel)"],
            "type": "containers"
        }
    ]
    
    # Format prefixes
    if prefix_patterns:
        result.append("\nPrefixes:")
        for prefix in prefix_patterns:
            result.append(f"\n{prefix['form']} = {prefix['function']}")
            if "examples" in prefix and prefix["examples"]:
                result.append("  Examples:")
                for ex in prefix["examples"]:
                    result.append(f"  - {ex}")
    
    # Format suffixes
    if suffix_patterns:
        result.append("\nSuffixes:")
        for suffix in suffix_patterns:
            result.append(f"\n{suffix['form']} = {suffix['function']}")
            if "examples" in suffix and suffix["examples"]:
                result.append("  Examples:")
                for ex in suffix["examples"]:
                    result.append(f"  - {ex}")
    
    return "\n".join(result)

def show_language_info() -> str:
    """Show information about the Woccon language"""
    info = """
Woccon Language Information
===========================

Historical Context:
------------------
Woccon was an Eastern Siouan language spoken by the Woccon people who lived in what is now eastern North Carolina, primarily along the Neuse River basin. The language is documented primarily through a wordlist of approximately 140 terms collected by John Lawson in 1709.

Linguistic Classification:
-------------------------
• Family: Siouan
• Branch: Eastern Siouan (Catawba-Woccon)
• Related to: Catawba, Tutelo, and other Eastern Siouan languages

Documentation:
-------------
The primary source for Woccon is John Lawson's "A New Voyage to Carolina" (1709), which contains the only known substantial wordlist of the language. Lawson collected these words during his travels through the Carolina colony, where he documented various Indigenous languages.

Current Status:
--------------
Woccon is considered a dormant language. The Woccon people were likely incorporated into neighboring tribes including the Tuscarora and Catawba following colonial pressures in the early 18th century.

Key Linguistic Features:
-----------------------
• Common roots like ya- (water), roo- (cloth/hide), yau- (path)
• Suffixes including -wa (natural phenomena), -he (animate beings)
• Regular sound correspondences with Catawba

This revitalization project aims to analyze the existing Woccon vocabulary to better understand the structure and patterns of the language, supporting educational and cultural heritage efforts.
"""
    return info

def main():
    """Main function for the CLI"""
    # Initialize WocconT5
    woccon = WocconT5()
    
    print("\n🗣️ Woccon Language CLI 🗣️")
    print("Type 'help' for available commands or 'quit' to exit")
    
    while True:
        try:
            user_input = input("\nwoccon> ").strip()
            
            # Handle empty input
            if not user_input:
                continue
            
            # Split into command and arguments
            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            # Process commands
            if command in ["quit", "exit", "q"]:
                print("Exiting Woccon CLI. Goodbye!")
                break
                
            elif command in ["help", "h", "?"]:
                print_help()
                
            elif command in ["lookup", "find", "l"]:
                if not args:
                    print("Please specify a word to look up")
                else:
                    result = lookup_word(woccon, args)
                    print(result)
                    
            elif command in ["analyze", "a"]:
                if not args:
                    print("Please specify a word to analyze")
                else:
                    result = analyze_word(woccon, args)
                    print(result)
                    
            elif command in ["category", "cat", "c"]:
                if not args:
                    print("Please specify a category to browse")
                else:
                    result = browse_category(woccon, args)
                    print(result)
                    
            elif command in ["roots", "root", "r"]:
                result = list_roots(woccon)
                print(result)
                
            elif command in ["affixes", "affix", "f"]:
                result = list_affixes(woccon)
                print(result)
                
            elif command in ["info", "i"]:
                result = show_language_info()
                print(result)
                
            else:
                print(f"Unknown command: {command}")
                print("Type 'help' for available commands")
                
        except KeyboardInterrupt:
            print("\nExiting Woccon CLI. Goodbye!")
            break
            
        except Exception as e:
            print(f"Error: {str(e)}")
    
if __name__ == "__main__":
    main()