import nltk
from nltk.corpus import words
import re

# Ensure the words corpus is downloaded
try:
    _ = words.words()
except LookupError:
    nltk.download('words')

ENGLISH_WORDS = set(words.words())

import string
import json
import os

CUSTOM_DICT_FILE = 'custom_dict.json'

def load_custom_dict():
    if os.path.exists(CUSTOM_DICT_FILE):
        with open(CUSTOM_DICT_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_custom_dict(d):
    with open(CUSTOM_DICT_FILE, 'w') as f:
        json.dump(d, f)

custom_dict = load_custom_dict()

def detect_gibberish(text):
    """
    Detects if the input text is gibberish or meaningful.
    Uses a hybrid approach: dictionary validation, pattern analysis, and an adaptive user dictionary.
    Returns: label: str
    """
    if not text.strip():
        return "Gibberish"

    # Tokenize input by splitting on whitespace to include alphanumeric tokens
    raw_tokens = text.lower().split()
    tokens = [t.strip(string.punctuation) for t in raw_tokens if t.strip(string.punctuation)]
    
    if not tokens:
        # No valid tokens found
        if re.search(r'\d', text):
            return "Mixed"
        return "Gibberish"

    valid_words = 0
    invalid_tokens = []
    
    for w in tokens:
        # It's valid if it's in standard English OR if the user has used it 2+ times in the past
        if w in ENGLISH_WORDS or custom_dict.get(w, 0) >= 2:
            valid_words += 1
        else:
            invalid_tokens.append(w)

    # Learn unrecognized words (Adaptation)
    for w in invalid_tokens:
        custom_dict[w] = custom_dict.get(w, 0) + 1
    
    if invalid_tokens:
        save_custom_dict(custom_dict)

    valid_ratio = valid_words / len(tokens)

    # Character pattern analysis (Vowel to consonant ratio, repetition)
    vowels = len(re.findall(r'[aeiouy]', text.lower()))

    consonants = len(re.findall(r'[bcdfghjklmnpqrstvwxz]', text.lower()))
    
    # Very low vowel ratio might indicate keyboard mashing (e.g. "sdfghjk")
    char_pattern_flag = False
    if consonants > 0:
        vc_ratio = vowels / consonants
        if vc_ratio < 0.1:
            char_pattern_flag = True

    # High repetition (e.g., "aaaaa")
    repetition_flag = bool(re.search(r'(.)\1{4,}', text))

    label = "Valid Text"

    if valid_ratio > 0.6 and not repetition_flag and not char_pattern_flag:
        label = "Valid Text"
    elif valid_ratio > 0.3:
        label = "Mixed"
    else:
        label = "Gibberish"

    return label
