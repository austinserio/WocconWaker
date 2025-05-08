# woccon_app.py - Main application entry point

from woccon_llama_integration import WocconAssistant
from woccon_enhancer import WocconEnhancer  # Your existing enhancer for linguistics
from woccon_orthographic_validator import FactualGuardRailIntegration  # New enhancer for orthographic accuracy
from main import WocconT5

def create_enhanced_assistant():
    """
    Create a fully enhanced WocconAssistant with both linguistic analysis
    capabilities and protection against hallucinating diacritical marks.
    """
    # Step 1: Create and enhance WocconT5 with linguistic capabilities
    woccon = WocconT5()
    linguistic_enhancer = WocconEnhancer(woccon, rules_path="woccon_language/rules.json")
    # Now woccon has enhanced linguistic analysis features
    
    # Step 2: Create assistant with the linguistically enhanced WocconT5
    assistant = WocconAssistant()
    
    # Step 3: Add factual guard rails to prevent hallucination
    fact_checker = FactualGuardRailIntegration(
        dict_path="woccon_language/dictionary.json",
        rules_path="woccon_language/rules.json"
    )
    enhanced_assistant = fact_checker.enhance_assistant(assistant)
    
    # Return the fully enhanced assistant
    return enhanced_assistant

if __name__ == "__main__":
    # Create the enhanced assistant
    assistant = create_enhanced_assistant()
    
    # Start CLI or server interaction
    print("\n🗣️  Woccon CLI — type 'control + C' to exit.\n")
    
    while True:
        try:
            msg = input("woccon> ").strip()
            if msg.lower() in ("quit", "exit"):
                break
            print("\n" + assistant.reply("cli_user", msg) + "\n")
        except KeyboardInterrupt:
            break