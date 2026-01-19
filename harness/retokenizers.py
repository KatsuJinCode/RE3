"""
Re-tokenization Transformers for RE3.

Each transformer takes text A and produces text B with the same semantic
content but different tokenization characteristics.
"""

import re
from typing import Callable, Dict

# Number words for B6b
NUMBER_WORDS = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
    '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine',
    '10': 'ten', '11': 'eleven', '12': 'twelve', '13': 'thirteen',
    '14': 'fourteen', '15': 'fifteen', '16': 'sixteen', '17': 'seventeen',
    '18': 'eighteen', '19': 'nineteen', '20': 'twenty', '30': 'thirty',
    '40': 'forty', '50': 'fifty', '60': 'sixty', '70': 'seventy',
    '80': 'eighty', '90': 'ninety'
}

# Common compound prefixes for B1e
COMPOUND_PREFIXES = ['un', 're', 'pre', 'dis', 'mis', 'non', 'over', 'under', 'out', 'sub']

# Simple syllable boundaries (consonant clusters)
SYLLABLE_PATTERN = re.compile(r'([aeiou]+[^aeiou]*)')


def b1a_camelcase_pairs(text: str) -> str:
    """
    B1a: CamelCase merge (pairs) - deterministic every-other-pair.

    "the quick brown fox" -> "theQuick brownFox"
    """
    words = text.split()
    result = []
    i = 0
    while i < len(words):
        if i + 1 < len(words):
            # Merge this word with next, capitalizing the second
            merged = words[i] + words[i + 1].capitalize()
            result.append(merged)
            i += 2
        else:
            result.append(words[i])
            i += 1
    return ' '.join(result)


def b1b_camelcase_all(text: str) -> str:
    """
    B1b: CamelCase merge (all) - join all words.

    "the quick brown fox" -> "theQuickBrownFox"
    """
    words = text.split()
    if not words:
        return text
    # First word lowercase, rest capitalized
    return words[0].lower() + ''.join(w.capitalize() for w in words[1:])


def b1c_underscore_join(text: str) -> str:
    """
    B1c: Replace spaces with underscores.

    "the quick brown" -> "the_quick_brown"
    """
    return text.replace(' ', '_')


def b1d_hyphenation(text: str) -> str:
    """
    B1d: Add hyphens at syllable-like boundaries for words > 6 chars.

    "understanding" -> "under-standing"

    Uses simple vowel-consonant heuristic.
    """
    def hyphenate_word(word: str) -> str:
        if len(word) <= 6:
            return word
        # Preserve non-alpha
        if not word.isalpha():
            return word
        # Find a reasonable split point (after first vowel cluster)
        match = re.search(r'^([^aeiou]*[aeiou]+[^aeiou]+)', word.lower())
        if match and len(match.group(1)) >= 2 and len(match.group(1)) < len(word) - 2:
            split_point = len(match.group(1))
            return word[:split_point] + '-' + word[split_point:]
        return word

    return ' '.join(hyphenate_word(w) for w in text.split())


def b1e_compound_split(text: str) -> str:
    """
    B1e: Split compounds at common prefix boundaries.

    "something" -> "some thing"
    "understand" -> "under stand"
    """
    def split_compound(word: str) -> str:
        if len(word) <= 6:
            return word
        lower = word.lower()
        for prefix in COMPOUND_PREFIXES:
            if lower.startswith(prefix) and len(word) > len(prefix) + 2:
                # Preserve original casing
                return word[:len(prefix)] + ' ' + word[len(prefix):]
        # Check for common suffixes
        if lower.endswith('thing') and len(word) > 7:
            return word[:-5] + ' ' + word[-5:]
        if lower.endswith('stand') and len(word) > 7:
            return word[:-5] + ' ' + word[-5:]
        return word

    return ' '.join(split_compound(w) for w in text.split())


def b2a_digit_spacing(text: str) -> str:
    """
    B2a: Add spaces between consecutive digits.

    "381" -> "3 8 1"
    "The answer is 42" -> "The answer is 4 2"
    """
    # Insert space between consecutive digits
    result = re.sub(r'(\d)(?=\d)', r'\1 ', text)
    return result


def b3a_lowercase_all(text: str) -> str:
    """
    B3a: Force all lowercase.

    "Hello World" -> "hello world"
    """
    return text.lower()


def b3b_uppercase_all(text: str) -> str:
    """
    B3b: Force all uppercase.

    "Hello World" -> "HELLO WORLD"
    """
    return text.upper()


def b4a_delimiter_swap(text: str) -> str:
    """
    B4a: Swap common delimiters.

    "###" -> "---"
    "---" -> "***"
    "***" -> "==="
    "===" -> "###"
    """
    swaps = [
        ('###', '---'),
        ('---', '***'),
        ('***', '==='),
        ('===', '###'),
        ('```', "'''"),
        ("'''", '```'),
    ]
    result = text
    # Use placeholder to avoid double-swapping
    for i, (old, new) in enumerate(swaps):
        placeholder = f"__DELIM_{i}__"
        result = result.replace(old, placeholder)
    for i, (old, new) in enumerate(swaps):
        placeholder = f"__DELIM_{i}__"
        result = result.replace(placeholder, new)
    return result


def b6b_word_numbers(text: str) -> str:
    """
    B6b: Convert digits to word form.

    "42" -> "forty-two"
    "The answer is 7" -> "The answer is seven"

    Handles numbers 0-99 and preserves larger numbers.
    """
    def num_to_words(n: int) -> str:
        if n < 0:
            return 'negative ' + num_to_words(-n)
        if n <= 20:
            return NUMBER_WORDS.get(str(n), str(n))
        if n < 100:
            tens = (n // 10) * 10
            ones = n % 10
            if ones == 0:
                return NUMBER_WORDS.get(str(tens), str(n))
            return NUMBER_WORDS.get(str(tens), str(tens)) + '-' + NUMBER_WORDS[str(ones)]
        return str(n)  # Keep large numbers as-is

    def replace_number(match):
        num_str = match.group(0)
        try:
            num = int(num_str)
            if 0 <= num < 100:
                return num_to_words(num)
        except ValueError:
            pass
        return num_str

    return re.sub(r'\b\d+\b', replace_number, text)


# Identity transformer for baseline
def identity(text: str) -> str:
    """No transformation - returns input unchanged."""
    return text


# Registry of all transformers
TRANSFORMERS: Dict[str, Callable[[str], str]] = {
    'none': identity,
    'b1a_camelcase_pairs': b1a_camelcase_pairs,
    'b1b_camelcase_all': b1b_camelcase_all,
    'b1c_underscore_join': b1c_underscore_join,
    'b1d_hyphenation': b1d_hyphenation,
    'b1e_compound_split': b1e_compound_split,
    'b2a_digit_spacing': b2a_digit_spacing,
    'b3a_lowercase_all': b3a_lowercase_all,
    'b3b_uppercase_all': b3b_uppercase_all,
    'b4a_delimiter_swap': b4a_delimiter_swap,
    'b6b_word_numbers': b6b_word_numbers,
}

# Strategies applicable to math benchmarks only
MATH_ONLY_STRATEGIES = {'b2a_digit_spacing', 'b6b_word_numbers'}

# Strategies applicable to all benchmarks
UNIVERSAL_STRATEGIES = set(TRANSFORMERS.keys()) - MATH_ONLY_STRATEGIES - {'none'}


def get_transformer(strategy_id: str) -> Callable[[str], str]:
    """Get transformer function by ID."""
    if strategy_id not in TRANSFORMERS:
        raise ValueError(f"Unknown strategy: {strategy_id}. Available: {list(TRANSFORMERS.keys())}")
    return TRANSFORMERS[strategy_id]


def apply_transform(text: str, strategy_id: str) -> str:
    """Apply a transformation strategy to text."""
    return get_transformer(strategy_id)(text)


if __name__ == "__main__":
    # Test each transformer
    test_text = "The quick brown fox jumps over 42 lazy dogs."

    print("Original:", test_text)
    print("-" * 60)

    for name, func in TRANSFORMERS.items():
        if name == 'none':
            continue
        result = func(test_text)
        print(f"{name}:")
        print(f"  {result}")
        print()
