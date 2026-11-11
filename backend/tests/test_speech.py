import unittest

from backend.speech import clean_text_for_speech


class SpeechCleaningTests(unittest.TestCase):
    def test_markdown_and_bullets(self):
        result = clean_text_for_speech("# Summary\n- **Revenue** fell *today*.\n1. Review the `price`.")
        self.assertEqual(result, "Summary Revenue fell today. Review the price.")

    def test_emojis_and_decorative_symbols(self):
        result = clean_text_for_speech("Great work! 🚀 ✨ — keep going.")
        self.assertEqual(result, "Great work! keep going.")

    def test_currency_percentages_and_compact_numbers(self):
        result = clean_text_for_speech("Reduce the price to ₹999, conversion is 25%, and sales reached 2.5K.")
        self.assertEqual(result, "Reduce the price to nine hundred ninety-nine rupees, conversion is twenty-five percent, and sales reached two point five thousand.")

    def test_links_keep_readable_text(self):
        result = clean_text_for_speech("Read [the seller report](https://example.com/report) for details.")
        self.assertEqual(result, "Read the seller report for details.")

    def test_code_fences_are_not_spoken(self):
        result = clean_text_for_speech("Use this:\n```python\nprint('secret')\n``` Done.")
        self.assertEqual(result, "Use this: Done.")

    def test_mixed_language_text_is_preserved(self):
        result = clean_text_for_speech("नमस्ते, your बिक्री is up 10%.")
        self.assertEqual(result, "नमस्ते, your बिक्री is up ten percent.")

    def test_abbreviations_are_spoken_as_letters(self):
        self.assertEqual(clean_text_for_speech("The AI KAM checked the ROI."), "The A I K A M checked the R O I.")


if __name__ == "__main__":
    unittest.main()