"""Tests for the SayLang natural-English translator (offline + mocked LLM)."""

import json
import ssl
import unittest
from unittest.mock import patch

from saylang.errors import SayTranslateError
from saylang.interpreter import run_and_capture
from saylang.translator import _build_ssl_context, translate_english


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class TestTranslator(unittest.TestCase):
    def test_offline_translation_and_execution(self) -> None:
        eng = (
            "create a variable score equal to 10. "
            "add 5 to score. "
            'if score is bigger than 12 then print "high score".'
        )
        res = translate_english(eng, provider="offline")
        self.assertEqual(res.backend, "offline")
        out, _ = run_and_capture(res.say_code)
        self.assertEqual(out.strip(), "high score")

    def test_offline_count_loop_and_function(self) -> None:
        eng = (
            "define a function double that takes x and returns x multiplied by 2\n"
            "count from 1 to 3 and print each number"
        )
        res = translate_english(eng, provider="offline")
        out, _ = run_and_capture(res.say_code)
        self.assertEqual(out.splitlines(), ["1", "2", "3"])

    def test_offline_repeat_and_colored_print(self) -> None:
        res = translate_english("loop 2 times and print hi", provider="offline")
        out, _ = run_and_capture(res.say_code)
        self.assertEqual(out.splitlines(), ["hi", "hi"])

        res_color = translate_english(
            "print hello world lol in red", provider="offline"
        )
        self.assertEqual(res_color.say_code, 'say "hello world lol" colour red')
        out_color, _ = run_and_capture(res_color.say_code)
        self.assertEqual(out_color, "\x1b[31mhello world lol\x1b[0m\n")

    def test_offline_unmatched_raises_helpful_error(self) -> None:
        with self.assertRaises(SayTranslateError) as ctx:
            translate_english("frobnicate the quantum widget", provider="offline")
        self.assertIn("GEMINI_API_KEY", ctx.exception.message)

    def test_llm_gemini_with_retry_on_invalid_syntax(self) -> None:
        replies = [
            "```saylang\nset x to [broken]\n```",
            "```saylang\nset x to 42\nsay x\n```",
        ]

        seen_contexts: list[object] = []

        def fake_urlopen(
            req: object, timeout: int = 30, context: object = None
        ) -> _FakeHTTPResponse:
            seen_contexts.append(context)
            text = replies.pop(0)
            return _FakeHTTPResponse(
                {"candidates": [{"content": {"parts": [{"text": text}]}}]}
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = translate_english(
                "set x to 42 and print it",
                provider="gemini",
                api_key="test-key",
            )
        self.assertEqual(res.backend, "gemini")
        self.assertTrue(all(isinstance(c, ssl.SSLContext) for c in seen_contexts))
        self.assertIsInstance(_build_ssl_context(), ssl.SSLContext)
        self.assertIn("set x to 42", res.say_code)
        out, _ = run_and_capture(res.say_code)
        self.assertEqual(out.strip(), "42")

    def test_llm_openai_and_anthropic_payloads(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(
                {"choices": [{"message": {"content": 'say "from openai"'}}]}
            ),
        ):
            res_oai = translate_english(
                "say hello", provider="openai", api_key="oai-key"
            )
            self.assertEqual(res_oai.say_code, 'say "from openai"')

        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(
                {"content": [{"type": "text", "text": 'say "from claude"'}]}
            ),
        ):
            res_ant = translate_english(
                "say hello", provider="anthropic", api_key="ant-key"
            )
            self.assertEqual(res_ant.say_code, 'say "from claude"')


if __name__ == "__main__":
    unittest.main()
