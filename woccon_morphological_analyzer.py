import re
from typing import Dict, List, Tuple, Optional, Set

class WocconMorphologicalAnalyzer:
    """Enhanced morphological analyzer for Woccon based on Blair Rudes' research"""
    
    def __init__(self, rules_json: Dict):
        """Initialize with rules from the updated rules.json"""
        self.rules = rules_json
        
        # Initialize phonological systems
        self._initialize_phonology()
        
        # Initialize morphological systems
        self._initialize_morphology()
    
    def _initialize_phonology(self):
        """Initialize phonological systems including vowel distinctions"""
        # Short oral vowels: i, e, a, u
        self.short_oral_vowels = {'i', 'e', 'a', 'u'}
        
        # Long oral vowels: i:, e:, a:, u:
        self.long_oral_vowels = {'i:', 'e:', 'a:', 'u:'}
        
        # Nasal vowels: ĩ, ẽ, ã, ũ
        self.nasal_vowels = {'ĩ', 'ẽ', 'ã', 'ũ'}
        
        # All vowels
        self.all_vowels = self.short_oral_vowels.union(self.long_oral_vowels).union(self.nasal_vowels)
        
        # Consonants with special behavior
        self.consonants = {
            'p': {'features': 'bilabial stop', 'voicing': False},
            't': {'features': 'alveolar stop', 'voicing': False},
            'k': {'features': 'velar stop', 'voicing': False},
            'č': {'features': 'palatal affricate', 'voicing': False},
            's': {'features': 'alveolar fricative', 'voicing': False},
            'h': {'features': 'glottal fricative', 'voicing': False},
            'm': {'features': 'bilabial nasal', 'voicing': True},
            'n': {'features': 'alveolar nasal', 'voicing': True},
            'r': {'features': 'liquid', 'voicing': True},
            'w': {'features': 'labial-velar approximant', 'voicing': True},
            'y': {'features': 'palatal approximant', 'voicing': True}
        }
        
        # Sound correspondences
        self.sound_correspondences = {}
        if 'sound_correspondences' in self.rules.get('phonology', {}):
            for corr in self.rules['phonology']['sound_correspondences'].get('Woccon_to_Catawba', []):
                self.sound_correspondences[corr['Woccon']] = {
                    'Catawba': corr['Catawba'],
                    'note': corr.get('note', '')
                }
    
    def _initialize_morphology(self):
        """Initialize morphological systems from rules.json"""
        # Extract affixes
        self.prefixes = []
        self.suffixes = []
        
        morphology = self.rules.get('morphology', {})
        affixes = morphology.get('affixes', {})
        
        if 'prefixes' in affixes:
            self.prefixes = affixes['prefixes']
        
        if 'suffixes' in affixes:
            self.suffixes = affixes['suffixes']
        
        # Extract common roots
        self.common_roots = morphology.get('common_roots', [])
        
        # Extract inflectional modes
        self.inflectional_modes = []
        if 'inflectional_morphology' in morphology:
            self.inflectional_modes = morphology['inflectional_morphology'].get('modes', [])
    
    def identify_inflectional_mode(self, word: str) -> Dict:
        """Identify the inflectional mode of a Woccon word"""
        word = word.lower().strip()
        
        for mode in self.inflectional_modes:
            marker = mode['marker']
            
            # Handle suffixes
            if marker.startswith('-'):
                clean_marker = marker.lstrip('-')
                if word.endswith(clean_marker):
                    return {
                        'mode': mode['name'],
                        'marker': marker,
                        'stem': word[:-len(clean_marker)],
                        'description': mode['description'],
                        'confidence': 'high'
                    }
            
            # Handle prefixes
            elif marker.endswith('-'):
                clean_marker = marker.rstrip('-')
                if word.startswith(clean_marker):
                    return {
                        'mode': mode['name'],
                        'marker': marker,
                        'stem': word[len(clean_marker):],
                        'description': mode['description'],
                        'confidence': 'high'
                    }
        
        # Default if no mode is identified
        return {
            'mode': 'unknown',
            'marker': None,
            'stem': word,
            'description': 'No inflectional mode identified',
            'confidence': 'low'
        }
    
    def detect_reduplication(self, word: str) -> Optional[Dict]:
        """Detect reduplication patterns in Woccon words"""
        word = word.lower().strip()
        
        # Check for full reduplication (like wawawa for snow)
        syllable_matches = []
        
        # Full three-part reduplication
        if len(word) >= 6 and word[:2] == word[2:4] == word[4:6]:
            return {
                'type': 'full_reduplication',
                'pattern': 'intensive',
                'base': word[:2],
                'confidence': 'high',
                'description': 'Intensive reduplication signaling high intensity'
            }
        
        # Two-part reduplication
        if len(word) >= 4:
            if word[:2] == word[2:4]:
                return {
                    'type': 'full_reduplication',
                    'pattern': 'moderate',
                    'base': word[:2],
                    'confidence': 'high',
                    'description': 'Moderate reduplication signaling frequency or intensity'
                }
        
        # Check for partial reduplication patterns
        if len(word) >= 6:
            # Check for patterns like kitkilare (break in pieces)
            if word[:3] == word[3:6]:
                return {
                    'type': 'partial_reduplication',
                    'pattern': 'frequentive',
                    'base': word[:3],
                    'confidence': 'medium',
                    'description': 'Frequentive reduplication showing repeated action'
                }
            
            # Check for pẽ:ʔpẽ:ʔ pattern (like in "mat")
            if '-' in word:
                parts = word.split('-')
                if len(parts) >= 2:
                    last_part = parts[-1]
                    if len(last_part) >= 8 and last_part[:4] == last_part[4:8]:
                        return {
                            'type': 'partial_reduplication',
                            'pattern': 'frequentive',
                            'base': last_part[:4],
                            'confidence': 'medium',
                            'description': 'Frequentive reduplication in compound word'
                        }
        
        return None
    
    def analyze_prefixes(self, word: str) -> List[Dict]:
        """Analyze prefixes in a Woccon word"""
        word = word.lower().strip()
        results = []
        
        for prefix in self.prefixes:
            prefix_form = prefix['form'].rstrip('-')
            
            if word.startswith(prefix_form):
                results.append({
                    'type': 'prefix',
                    'form': prefix['form'],
                    'function': prefix['function'],
                    'position': 'start',
                    'confidence': 'high',
                    'semantic_type': prefix.get('type', 'unknown')
                })
        
        return results
    
    def analyze_suffixes(self, word: str) -> List[Dict]:
        """Analyze suffixes in a Woccon word"""
        word = word.lower().strip()
        results = []
        
        for suffix in self.suffixes:
            suffix_form = suffix['form'].lstrip('-')
            
            if word.endswith(suffix_form):
                results.append({
                    'type': 'suffix',
                    'form': suffix['form'],
                    'function': suffix['function'],
                    'position': 'end',
                    'confidence': 'high',
                    'semantic_type': suffix.get('type', 'unknown')
                })
        
        return results
    
    def analyze_roots(self, word: str, english_meaning: str = "") -> List[Dict]:
        """Analyze roots in a Woccon word"""
        word = word.lower().strip()
        results = []
        
        for root_info in self.common_roots:
            root = root_info['root'].rstrip('-')
            clean_word = word.replace('-', '')
            
            # Direct prefix match
            if clean_word.startswith(root):
                confidence_score = 0.8
                match_type = "prefix"
                
                # Adjust confidence based on semantic relevance if meaning is provided
                if english_meaning:
                    confidence_score = self._adjust_root_confidence(
                        root_info, 
                        confidence_score,
                        word, 
                        english_meaning
                    )
                
                # Convert numerical confidence to text level
                confidence_level = "high" if confidence_score > 0.7 else "medium" if confidence_score > 0.4 else "low"
                
                results.append({
                    'root': root_info['root'],
                    'meaning': root_info['meaning'],
                    'derivatives': root_info.get('derivatives', []),
                    'match_type': match_type,
                    'confidence': confidence_level,
                    'confidence_score': confidence_score
                })
            
            # Compound element (occurs within the word)
            elif root in clean_word and len(root) > 1:
                confidence_score = 0.4
                match_type = "compound"
                
                # Adjust confidence based on semantic relevance if meaning is provided
                if english_meaning:
                    confidence_score = self._adjust_root_confidence(
                        root_info,
                        confidence_score,
                        word, 
                        english_meaning
                    )
                
                # Convert numerical confidence to text level
                confidence_level = "high" if confidence_score > 0.7 else "medium" if confidence_score > 0.4 else "low"
                
                results.append({
                    'root': root_info['root'],
                    'meaning': root_info['meaning'],
                    'derivatives': root_info.get('derivatives', []),
                    'match_type': match_type,
                    'confidence': confidence_level,
                    'confidence_score': confidence_score
                })
        
        # Sort roots by confidence score
        results.sort(key=lambda x: x['confidence_score'], reverse=True)
        return results
    
    def _adjust_root_confidence(self, root_info: Dict, base_score: float, word: str, meaning: str) -> float:
        """Adjust root confidence score based on semantic and morphological evidence"""
        root_meaning = root_info['meaning'].lower()
        meaning = meaning.lower()
        
        # Direct meaning match is strongest evidence
        if root_meaning in meaning:
            base_score += 0.3
            
        # Check derivatives for semantic matches
        for deriv in root_info.get('derivatives', []):
            if 'form' in deriv and deriv['form'].lower() == word:
                base_score += 0.4  # Direct match to a known derivative
                break
            elif 'meaning' in deriv and deriv['meaning'].lower() in meaning:
                base_score += 0.2
                break
                
        # Check for semantic field matches
        semantic_fields = {
            "water": ["water", "rain", "fish", "wet", "fluid", "river", "stream"],
            "path": ["path", "way", "walk", "move", "indian", "trail", "road"],
            "container": ["container", "vessel", "hold", "bottle", "gourd", "bowl"],
            "wood": ["wood", "tree", "box", "wooden", "forest", "log"],
            "cloth": ["cloth", "clothing", "wear", "blanket", "hide", "skin", "material"]
        }
        
        for field, terms in semantic_fields.items():
            if field in root_meaning:
                if any(term in meaning for term in terms):
                    base_score += 0.2
                    break
        
        # Adjust for known suffix combinations
        has_he_suffix = '-he' in word
        has_wa_suffix = '-wa' in word
        has_pe_suffix = '-pe' in word
        has_iune_suffix = '-iune' in word
        
        # Root ya- often appears with -wa suffix for natural phenomena
        if root_info['root'] == 'ya-' and has_wa_suffix:
            base_score += 0.3
            
        # Root yau- often appears with -he suffix for animate beings
        if root_info['root'] == 'yau-' and has_he_suffix:
            base_score += 0.3
        
        # Root ya- rarely appears with -he suffix
        if root_info['root'] == 'ya-' and has_he_suffix:
            base_score -= 0.3
            
        # Root watta- often appears with -pe suffix for containers
        if root_info['root'] == 'watta-' and has_pe_suffix:
            base_score += 0.3
            
        # Root roo- often appears with -iune suffix for manufactured items
        if root_info['root'] == 'roo-' and has_iune_suffix:
            base_score += 0.3
                    
        return min(base_score, 1.0)  # Cap at 1.0
    
    def analyze_word(self, word: str, english_meaning: str = "") -> Dict:
        """
        Perform a comprehensive morphological analysis of a Woccon word
        based on Blair Rudes' research
        """
        word = word.lower().strip()
        
        # Initialize analysis structure
        analysis = {
            "word": word,
            "meaning": english_meaning,
            "roots": [],
            "affixes": [],
            "reduplication": None,
            "inflectional_mode": None,
            "syllable_structure": self._analyze_syllables(word)
        }
        
        # Analyze roots
        analysis["roots"] = self.analyze_roots(word, english_meaning)
        
        # Analyze prefixes
        prefix_analysis = self.analyze_prefixes(word)
        if prefix_analysis:
            analysis["affixes"].extend(prefix_analysis)
            
        # Analyze suffixes
        suffix_analysis = self.analyze_suffixes(word)
        if suffix_analysis:
            analysis["affixes"].extend(suffix_analysis)
            
        # Analyze reduplication
        reduplication = self.detect_reduplication(word)
        if reduplication:
            analysis["reduplication"] = reduplication
            
        # Analyze inflectional mode
        inflectional_mode = self.identify_inflectional_mode(word)
        if inflectional_mode["mode"] != "unknown":
            analysis["inflectional_mode"] = inflectional_mode
            
        return analysis
    
    def _analyze_syllables(self, word: str) -> List[str]:
        """Analyze the syllable structure of a Woccon word"""
        word = word.lower().replace('-', '')
        
        # Convert to a more standardized form for processing
        # Handle common digraphs and special characters
        standardized = word
        for c in "ĩẽãũ":
            if c in standardized:
                standardized = standardized.replace(c, c.replace('̃', '') + 'N')  # Mark nasal vowels
        
        for digraph in ["au", "oo", "ee", "ai"]:
            if digraph in standardized:
                replacement = digraph.upper()
                standardized = standardized.replace(digraph, replacement)
        
        # Find syllable boundaries
        syllables = []
        current = ""
        i = 0
        
        while i < len(standardized):
            current += standardized[i]
            
            # Check if we have a vowel (including our marked digraphs and nasals)
            is_vowel = standardized[i] in "ieauIEAUNOO"
            
            # If we have a vowel and there are more characters
            if is_vowel and i < len(standardized) - 1:
                # If the next character is a consonant
                if standardized[i+1] not in "ieauIEAUNOO":
                    # Check if there's another consonant after (consonant cluster)
                    if i < len(standardized) - 2 and standardized[i+2] not in "ieauIEAUNOO":
                        syllables.append(current)
                        current = ""
                    # Or if it's the end of the word
                    elif i == len(standardized) - 2:
                        current += standardized[i+1]
                        syllables.append(current)
                        current = ""
                        break
            
            i += 1
        
        # Add any remaining syllable
        if current:
            syllables.append(current)
        
        # Convert back to original representation
        result = []
        for syllable in syllables:
            # Convert marked nasals back
            for c in "ieau":
                if c + "N" in syllable:
                    syllable = syllable.replace(c + "N", c + "̃")
            
            # Convert marked digraphs back
            syllable = syllable.replace("AU", "au").replace("OO", "oo").replace("EE", "ee").replace("AI", "ai")
            result.append(syllable)
        
        return result