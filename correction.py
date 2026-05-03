import re
import json
import os
from textblob import TextBlob

# Normalization map for visually similar numbers and symbols to letters
LEET_MAP = {
    '0': 'o', '3': 'e', '4': 'a', '5': 's', '1': 'i', '7': 't',
    '@': 'a', '!': 'i', '^': 'a'
}

class AdaptiveCorrector:
    """
    Acts as a simple probabilistic ML model (similar to Naive Bayes frequency counting).
    It learns from previously corrected words and adapts from past mistakes.
    """
    def __init__(self, memory_file='ml_correction_model.json'):
        self.memory_file = memory_file
        self.memory = self.load_memory()

    def load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r') as f:
                return json.load(f)
        return {}

    def save_memory(self):
        with open(self.memory_file, 'w') as f:
            json.dump(self.memory, f)

    def predict(self, word):
        # Look up the probabilistic frequency of past corrections
        if word in self.memory:
            freq_map = self.memory[word]
            best_correction = max(freq_map.items(), key=lambda x: x[1])[0]
            return best_correction
        return None

    def learn(self, bad_word, corrected_word):
        if bad_word == corrected_word:
            return
        if bad_word not in self.memory:
            self.memory[bad_word] = {}
        if corrected_word not in self.memory[bad_word]:
            self.memory[bad_word][corrected_word] = 0
        self.memory[bad_word][corrected_word] += 1
        self.save_memory()
        
    def force_learn(self, bad_word, corrected_word):
        if bad_word not in self.memory:
            self.memory[bad_word] = {}
        # Grant it a massive frequency distribution to permanently override organic errors
        self.memory[bad_word][corrected_word] = 99999
        self.save_memory()

ml_model = AdaptiveCorrector()

def manual_train(bad_word, good_word):
    ml_model.force_learn(bad_word.lower(), good_word.lower())

def normalize_text(text):
    normalized = ""
    for char in text:
        if char in LEET_MAP:
            normalized += LEET_MAP[char]
        else:
            normalized += char

    # Advanced algorithm:
    # If there are stray numbers or unknown symbols left embedded inside letters (e.g. p*ragraph, th2t),
    # striking them out (pragraph, tht) dramatically improves the bayesian probabilities of TextBlob.
    import string
    
    # Tokenize preserving exact whitespace layout (newlines, tabs, spaces)
    tokens = re.split(r'(\s+)', normalized)
    processed_tokens = []
    
    for w in tokens:
        if not w.strip(): # keep whitespace layout intact
            processed_tokens.append(w)
            continue
            
        if any(c.isalpha() for c in w):
            # Preserve trailing punctuation (like ! ? . ,)
            trailing_punct = ""
            while w and w[-1] in string.punctuation.replace("'", ""): # don't treat ' at end as trailing punct usually? just all punct
                if w[-1] in string.punctuation:
                    trailing_punct = w[-1] + trailing_punct
                    w = w[:-1]
            
            # Strip all embedded numbers and symbols (except apostrophes for contractions)
            w_clean = ""
            for c in w:
                if c.isalpha() or c == "'":
                    w_clean += c
                    
            w = w_clean + trailing_punct
            
        processed_tokens.append(w)
        
    return "".join(processed_tokens)

def correct_text(text):
    """
    Normalizes text, utilizes the ML Adaptive Model, and falls back to TextBlob spell/grammar correction.
    Returns the corrected text string.
    """
    if not text.strip():
        return ""
        
    normalized = normalize_text(text)
    
    # Remove consecutive repeated words (e.g., "is is" -> "is")
    normalized = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', normalized, flags=re.IGNORECASE)
    
    # Process word by word via layout-preserving split
    tokens = re.split(r'(\s+)', normalized)
    final_tokens = []
    
    for w in tokens:
        if not w.strip(): # preserve whitespace layout
            final_tokens.append(w)
            continue
            
        # Check ML model prediction first
        prediction = ml_model.predict(w)
        if prediction:
            final_tokens.append(prediction)
        else:
            # Fallback to TextBlob naive bayes correction
            blob = TextBlob(w)
            corrected_w = str(blob.correct())
            final_tokens.append(corrected_w)
            
            # Train the ML model from this instance for future adaptation
            ml_model.learn(w, corrected_w)
            
    corrected = "".join(final_tokens)
    
    return corrected
