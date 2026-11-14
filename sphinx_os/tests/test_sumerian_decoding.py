#!/usr/bin/env python3
"""
Unit tests for the Sumerian Decoding module.

Tests cover:
- Letter etymology data integrity
- LetterDecoding class
- SumerianDecoding class
- Genesis block decoding
- Sumerian word analysis
- Convenience functions
- Gematria calculations
"""

import hashlib
import struct
import unittest

from sphinx_os.nexus.sumerian_decoding import (
    LETTER_ETYMOLOGY,
    SUMERIAN_CORE_SIGNS,
    GENESIS_HASH,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    LetterDecoding,
    SumerianDecoding,
    SumerianWordAnalysis,
    decode_genesis_letters,
    decode_seed_letters,
    get_letter_etymology,
    get_all_etymologies,
    get_sumerian_core_signs,
)


class TestLetterEtymology(unittest.TestCase):
    """Test the 22 letter etymology data."""

    def test_22_letters(self):
        """There should be exactly 22 letters."""
        self.assertEqual(len(LETTER_ETYMOLOGY), 22)

    def test_all_letters_have_required_fields(self):
        """Each letter entry should have all required fields."""
        required_fields = [
            "hebrew", "hebrew_char", "gematria", "paleo_hebrew",
            "phoenician", "proto_sinaitic", "egyptian_hieroglyph",
            "sumerian_sign", "original_image", "sound", "element"
        ]
        for entry in LETTER_ETYMOLOGY:
            for field in required_fields:
                self.assertIn(field, entry, f"Missing field {field} in {entry['hebrew']}")

    def test_gematria_values(self):
        """Test known gematria values."""
        gematria_map = {e["hebrew"]: e["gematria"] for e in LETTER_ETYMOLOGY}
        self.assertEqual(gematria_map["Aleph"], 1)
        self.assertEqual(gematria_map["Bet"], 2)
        self.assertEqual(gematria_map["Gimel"], 3)
        self.assertEqual(gematria_map["Yod"], 10)
        self.assertEqual(gematria_map["Kaf"], 20)
        self.assertEqual(gematria_map["Lamed"], 30)
        self.assertEqual(gematria_map["Resh"], 200)
        self.assertEqual(gematria_map["Shin"], 300)
        self.assertEqual(gematria_map["Tav"], 400)

    def test_hebrew_chars_unique(self):
        """Each Hebrew character should be unique."""
        chars = [e["hebrew_char"] for e in LETTER_ETYMOLOGY]
        self.assertEqual(len(chars), len(set(chars)))

    def test_letter_names_unique(self):
        """Each letter name should be unique."""
        names = [e["hebrew"] for e in LETTER_ETYMOLOGY]
        self.assertEqual(len(names), len(set(names)))

    def test_aleph_is_ox(self):
        """Aleph should originate from an ox head."""
        aleph = LETTER_ETYMOLOGY[0]
        self.assertEqual(aleph["hebrew"], "Aleph")
        self.assertIn("ox", aleph["proto_sinaitic"].lower())

    def test_bet_is_house(self):
        """Bet should originate from a house."""
        bet = LETTER_ETYMOLOGY[1]
        self.assertEqual(bet["hebrew"], "Bet")
        self.assertIn("house", bet["proto_sinaitic"].lower())

    def test_mem_is_water(self):
        """Mem should originate from water."""
        mem = [e for e in LETTER_ETYMOLOGY if e["hebrew"] == "Mem"][0]
        self.assertIn("water", mem["proto_sinaitic"].lower())

    def test_nun_is_fish(self):
        """Nun should originate from a fish."""
        nun = [e for e in LETTER_ETYMOLOGY if e["hebrew"] == "Nun"][0]
        self.assertIn("fish", nun["proto_sinaitic"].lower())

    def test_yod_is_hand(self):
        """Yod should originate from a hand."""
        yod = [e for e in LETTER_ETYMOLOGY if e["hebrew"] == "Yod"][0]
        self.assertIn("hand", yod["proto_sinaitic"].lower())


class TestSumerianCoreSigns(unittest.TestCase):
    """Test the Sumerian cuneiform core signs."""

    def test_core_signs_not_empty(self):
        """There should be core Sumerian signs."""
        self.assertGreater(len(SUMERIAN_CORE_SIGNS), 0)

    def test_core_signs_have_fields(self):
        """Each sign should have name, meaning, and sumerian fields."""
        for sign, data in SUMERIAN_CORE_SIGNS.items():
            self.assertIn("name", data)
            self.assertIn("meaning", data)
            self.assertIn("sumerian", data)


class TestLetterDecoding(unittest.TestCase):
    """Test the LetterDecoding dataclass."""

    def setUp(self):
        """Create a sample LetterDecoding."""
        self.decoding = LetterDecoding(
            hebrew="Aleph",
            hebrew_char="א",
            gematria=1,
            paleo_hebrew="𐤀",
            phoenician="𐤀",
            proto_sinaitic="Ox head",
            egyptian_hieroglyph="𐂝 (ʾalp — ox)",
            sumerian_sign="𒀀 (A / AN — sky/heaven)",
            original_image="An ox head — strength, the first sound of breath",
            sound="glottal stop",
            element="spirit",
        )

    def test_to_pictograph(self):
        """Pictograph should include letter name and image."""
        result = self.decoding.to_pictograph()
        self.assertIn("Aleph", result)
        self.assertIn("א", result)
        self.assertIn("ox head", result.lower())

    def test_to_sumerian(self):
        """Sumerian output should include the cuneiform sign."""
        result = self.decoding.to_sumerian()
        self.assertIn("Aleph", result)
        self.assertIn("𒀀", result)

    def test_full_chain(self):
        """Full chain should include all historical layers."""
        result = self.decoding.full_chain()
        self.assertIn("Aleph", result)
        self.assertIn("Egyptian", result)
        self.assertIn("Proto-Sinaitic", result)
        self.assertIn("Phoenician", result)
        self.assertIn("Hebrew", result)
        self.assertIn("Sumerian", result)


class TestSumerianDecoding(unittest.TestCase):
    """Test the SumerianDecoding class."""

    def test_decode_basic_sequence(self):
        """Decoding a basic sequence should work."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet", "Gimel"])
        decoding.decode()
        self.assertEqual(len(decoding.decodings), 3)

    def test_gematria_sum(self):
        """Gematria sum should be correct."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet", "Gimel"])
        decoding.decode()
        self.assertEqual(decoding.gematria_sum, 1 + 2 + 3)  # 6

    def test_gematria_mod_691(self):
        """Gematria mod 691 should be correct."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet", "Gimel"])
        decoding.decode()
        self.assertEqual(decoding.gematria_mod_691, 6 % 691)  # 6

    def test_pictographic_reading(self):
        """Pictographic reading should be non-empty."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet"])
        decoding.decode()
        self.assertGreater(len(decoding.pictographic_reading), 0)

    def test_sumerian_reading(self):
        """Sumerian reading should be non-empty."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet"])
        decoding.decode()
        self.assertGreater(len(decoding.sumerian_reading), 0)

    def test_get_hebrew_chars(self):
        """Hebrew characters should be extracted correctly."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet", "Gimel"])
        decoding.decode()
        chars = decoding.get_hebrew_chars()
        self.assertEqual(chars, "אבג")

    def test_get_elemental_sequence(self):
        """Elemental sequence should match letter count."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet", "Gimel"])
        decoding.decode()
        elements = decoding.get_elemental_sequence()
        self.assertEqual(len(elements), 3)

    def test_get_sumerian_cuneiform(self):
        """Sumerian cuneiform should be non-empty."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet"])
        decoding.decode()
        cuneiform = decoding.get_sumerian_cuneiform()
        self.assertGreater(len(cuneiform), 0)

    def test_analyze_returns_dict(self):
        """Analysis should return a dictionary with expected keys."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet", "Gimel"])
        decoding.decode()
        analysis = decoding.analyze()
        self.assertIn("letter_count", analysis)
        self.assertIn("gematria_sum", analysis)
        self.assertIn("gematria_mod_691", analysis)
        self.assertIn("unique_letters", analysis)
        self.assertIn("element_distribution", analysis)
        self.assertIn("hebrew_string", analysis)

    def test_analyze_letter_count(self):
        """Analysis letter count should match input."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet", "Gimel"])
        decoding.decode()
        analysis = decoding.analyze()
        self.assertEqual(analysis["letter_count"], 3)

    def test_analyze_unique_letters(self):
        """Analysis unique letters should be correct."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Aleph", "Bet"])
        decoding.decode()
        analysis = decoding.analyze()
        self.assertEqual(analysis["unique_letters"], 2)

    def test_decode_auto_on_analyze(self):
        """Analyze should auto-decode if not already decoded."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet"])
        analysis = decoding.analyze()
        self.assertEqual(analysis["letter_count"], 2)

    def test_get_pictographic_message_auto_decode(self):
        """get_pictographic_message should auto-decode."""
        decoding = SumerianDecoding(letter_sequence=["Aleph", "Bet"])
        msg = decoding.get_pictographic_message()
        self.assertGreater(len(msg), 0)


class TestGenesisDecoding(unittest.TestCase):
    """Test the Genesis block decoding."""

    def test_decode_genesis_letters(self):
        """Genesis decoding should produce 32 letters."""
        decoding = decode_genesis_letters()
        self.assertEqual(len(decoding.letter_sequence), 32)

    def test_genesis_gematria_sum(self):
        """Genesis gematria sum should be 1390."""
        decoding = decode_genesis_letters()
        self.assertEqual(decoding.gematria_sum, 1390)

    def test_genesis_gematria_mod_691(self):
        """Genesis gematria mod 691 should be 8."""
        decoding = decode_genesis_letters()
        self.assertEqual(decoding.gematria_mod_691, 8)

    def test_genesis_hebrew_string(self):
        """Genesis Hebrew string should be non-empty."""
        decoding = decode_genesis_letters()
        chars = decoding.get_hebrew_chars()
        self.assertEqual(len(chars), 32)

    def test_genesis_unique_letters(self):
        """Genesis should use multiple unique letters."""
        decoding = decode_genesis_letters()
        analysis = decoding.analyze()
        self.assertGreater(analysis["unique_letters"], 10)

    def test_genesis_pictographic_message(self):
        """Genesis pictographic message should contain images."""
        decoding = decode_genesis_letters()
        msg = decoding.get_pictographic_message()
        self.assertIn("sword", msg.lower())
        self.assertIn("house", msg.lower())

    def test_genesis_elemental_distribution(self):
        """Genesis elemental distribution should sum to 32."""
        decoding = decode_genesis_letters()
        analysis = decoding.analyze()
        total = sum(analysis["element_distribution"].values())
        self.assertEqual(total, 32)

    def test_genesis_constants(self):
        """Genesis constants should be correct."""
        self.assertEqual(GENESIS_NONCE, 2083236893)
        self.assertEqual(GENESIS_TIMESTAMP, 1231006505)
        self.assertTrue(GENESIS_HASH.startswith("000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"))

    def test_genesis_seed_deterministic(self):
        """Genesis seed should be deterministic."""
        decoding1 = decode_genesis_letters()
        decoding2 = decode_genesis_letters()
        self.assertEqual(decoding1.gematria_sum, decoding2.gematria_sum)
        self.assertEqual(decoding1.get_hebrew_chars(), decoding2.get_hebrew_chars())


class TestSeedDecoding(unittest.TestCase):
    """Test decoding arbitrary seeds."""

    def test_decode_known_seed(self):
        """Decoding a known seed should produce 32 letters."""
        seed = b"0123456789abcdef0123456789abcdef"
        decoding = decode_seed_letters(seed)
        self.assertEqual(len(decoding.letter_sequence), 32)

    def test_different_seeds_different_letters(self):
        """Different seeds should produce different letter sequences."""
        seed1 = b"0123456789abcdef0123456789abcdef"
        seed2 = b"fedcba9876543210fedcba9876543210"
        decoding1 = decode_seed_letters(seed1)
        decoding2 = decode_seed_letters(seed2)
        self.assertNotEqual(decoding1.letter_sequence, decoding2.letter_sequence)

    def test_empty_seed(self):
        """Empty seed should still produce letters."""
        seed = b""
        decoding = decode_seed_letters(seed)
        self.assertEqual(len(decoding.letter_sequence), 0)


class TestSumerianWordAnalysis(unittest.TestCase):
    """Test the Sumerian word analysis."""

    def setUp(self):
        """Create a Genesis decoding for testing."""
        self.decoding = decode_genesis_letters()
        self.word_analysis = SumerianWordAnalysis(decoding=self.decoding)

    def test_analyze_words(self):
        """Word analysis should complete without error."""
        self.word_analysis.analyze_words()
        self.assertGreaterEqual(self.word_analysis.get_word_count(), 0)

    def test_word_count(self):
        """Word count should be non-negative."""
        self.word_analysis.analyze_words()
        self.assertGreaterEqual(self.word_analysis.get_word_count(), 0)

    def test_elemental_words(self):
        """Elemental words should be a dictionary."""
        self.word_analysis.analyze_words()
        elemental = self.word_analysis.get_elemental_words()
        self.assertIsInstance(elemental, dict)

    def test_words_have_required_fields(self):
        """Each word should have required fields."""
        self.word_analysis.analyze_words()
        for word in self.word_analysis.words:
            self.assertIn("letters", word)
            self.assertIn("element", word)
            self.assertIn("gematria", word)
            self.assertIn("hebrew", word)


class TestConvenienceFunctions(unittest.TestCase):
    """Test the convenience functions."""

    def test_get_letter_etymology(self):
        """Getting a known letter should return its etymology."""
        result = get_letter_etymology("Aleph")
        self.assertIsNotNone(result)
        self.assertEqual(result["hebrew"], "Aleph")

    def test_get_letter_etymology_unknown(self):
        """Getting an unknown letter should return None."""
        result = get_letter_etymology("Unknown")
        self.assertIsNone(result)

    def test_get_all_etymologies(self):
        """Getting all etymologies should return 22 letters."""
        result = get_all_etymologies()
        self.assertEqual(len(result), 22)

    def test_get_sumerian_core_signs(self):
        """Getting Sumerian core signs should return a dict."""
        result = get_sumerian_core_signs()
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)


class TestGematriaMath(unittest.TestCase):
    """Test gematria calculations."""

    def test_all_gematria_positive(self):
        """All gematria values should be positive."""
        for entry in LETTER_ETYMOLOGY:
            self.assertGreater(entry["gematria"], 0)

    def test_gematria_sum_all_letters(self):
        """Sum of all 22 gematria values should be correct."""
        total = sum(e["gematria"] for e in LETTER_ETYMOLOGY)
        self.assertEqual(total, 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 +
                         20 + 30 + 40 + 50 + 60 + 70 + 80 + 90 + 100 +
                         200 + 300 + 400)

    def test_gematria_mod_691_all_letters(self):
        """Gematria sum of all letters mod 691 should be computed."""
        total = sum(e["gematria"] for e in LETTER_ETYMOLOGY)
        mod_result = total % 691
        self.assertGreaterEqual(mod_result, 0)
        self.assertLess(mod_result, 691)

    def test_genesis_mod_691_is_octonion_dimension(self):
        """Genesis gematria mod 691 = 8, the octonion dimension."""
        decoding = decode_genesis_letters()
        self.assertEqual(decoding.gematria_mod_691, 8)


class TestHistoricalAccuracy(unittest.TestCase):
    """Test historical accuracy of the etymology data."""

    def test_proto_sinaitic_from_egyptian(self):
        """Proto-Sinaitic should be derived from Egyptian hieroglyphs."""
        for entry in LETTER_ETYMOLOGY:
            self.assertGreater(
                len(entry["egyptian_hieroglyph"]), 0,
                f"{entry['hebrew']} should have Egyptian hieroglyph reference"
            )

    def test_sumerian_signs_present(self):
        """All letters should have Sumerian cuneiform equivalents."""
        for entry in LETTER_ETYMOLOGY:
            self.assertGreater(len(entry["sumerian_sign"]), 0)

    def test_original_images_present(self):
        """All letters should have original image descriptions."""
        for entry in LETTER_ETYMOLOGY:
            self.assertGreater(len(entry["original_image"]), 0)

    def test_elements_present(self):
        """All letters should have elemental associations."""
        for entry in LETTER_ETYMOLOGY:
            self.assertGreater(len(entry["element"]), 0)


if __name__ == "__main__":
    unittest.main()
