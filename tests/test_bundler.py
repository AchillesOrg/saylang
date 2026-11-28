"""Tests for standalone native binary bundling in SayLang."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from saylang.bundler import (
    EmbeddedApp,
    build_standalone_binary,
    decode_bundle_trailer,
    encode_bundle_trailer,
    read_embedded_app,
    strip_existing_trailer,
)
from saylang.cli import _run_embedded_if_present, main
from saylang.errors import SayError


class TestBundler(unittest.TestCase):
    def test_encode_decode_strip_and_tail_read(self) -> None:
        host = b"\xcf\xfa\xed\xfe" + b"\x00" * 128
        src = 'say "Hello"\n'
        trailer = encode_bundle_trailer(src, name="greet.pl")
        combined = host + trailer

        self.assertEqual(strip_existing_trailer(combined), host)
        self.assertEqual(strip_existing_trailer(host), host)

        decoded = decode_bundle_trailer(combined)
        self.assertEqual(decoded, EmbeddedApp(name="greet.pl", source=src))
        self.assertIsNone(decode_bundle_trailer(host))
        self.assertIsNone(decode_bundle_trailer(combined[:-3]))

        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = Path(tmpdir) / "greet_bin"
            bin_path.write_bytes(combined)
            self.assertEqual(
                read_embedded_app(bin_path), EmbeddedApp(name="greet.pl", source=src)
            )
            plain_path = Path(tmpdir) / "plain_bin"
            plain_path.write_bytes(host)
            self.assertIsNone(read_embedded_app(plain_path))

    def test_run_embedded_executes_flags_and_help(self) -> None:
        src = (
            "flags: -d\n"
            "if flag -d\n"
            '    say "with date"\n'
            "otherwise\n"
            '    say "plain"\n'
        )
        host = b"\x7fELF" + b"\x00" * 64
        with tempfile.TemporaryDirectory() as tmpdir:
            exe = Path(tmpdir) / "clock_bin"
            exe.write_bytes(host + encode_bundle_trailer(src, name="clock.pl"))

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = _run_embedded_if_present(exe, ["-d"], prog_name="clock_bin")
            self.assertEqual(rc, 0)
            self.assertEqual(out.getvalue(), "with date\n")

            help_out = io.StringIO()
            with contextlib.redirect_stdout(help_out):
                rc = _run_embedded_if_present(exe, ["--help"], prog_name="clock_bin")
            self.assertEqual(rc, 0)
            self.assertIn("Usage: clock_bin [-d]", help_out.getvalue())

    def test_cli_build_and_compile_bin_with_mock_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime = tmp / "saylang_host"
            runtime.write_bytes(b"\x7fELF" + b"\x11" * 64)
            script = tmp / "app.pl"
            script.write_text('say "built ok"\n', encoding="utf-8")

            out1 = tmp / "app1"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["build", str(script), "-o", str(out1), "--runtime", str(runtime)])
            self.assertEqual(rc, 0)
            self.assertIn("Built standalone binary:", buf.getvalue())
            built_file = out1 if out1.is_file() else Path(f"{out1}.exe")
            self.assertTrue(built_file.is_file())
            self.assertEqual(
                read_embedded_app(built_file),
                EmbeddedApp(name="app.pl", source='say "built ok"\n'),
            )

            out2 = tmp / "app2"
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                rc2 = main(
                    ["compile", str(script), "--bin", "-o", str(out2), "--runtime", str(runtime)]
                )
            self.assertEqual(rc2, 0)
            self.assertIn("Built standalone binary:", buf2.getvalue())

    def test_build_rejects_syntax_error_and_rebuilds_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime = tmp / "saylang_host"
            # Pre-populate host with an old trailer to verify strip_existing_trailer runs cleanly.
            raw_host = b"\xcf\xfa\xed\xfe" + b"\x22" * 64
            runtime.write_bytes(raw_host + encode_bundle_trailer('say "old"\n', name="old.pl"))

            bad = tmp / "bad.pl"
            bad.write_text("if true\nsay 1\n", encoding="utf-8")
            with self.assertRaises(SayError):
                build_standalone_binary(bad, output_path=tmp / "bad_bin", runtime_binary=runtime)
            self.assertFalse((tmp / "bad_bin").exists())
            self.assertFalse((tmp / "bad_bin.exe").exists())

            good = tmp / "good.pl"
            good.write_text('say "fresh"\n', encoding="utf-8")
            with patch("saylang.bundler._runtime_supports_embedding", return_value=True):
                res = build_standalone_binary(
                    good, output_path=tmp / "good_bin", runtime_binary=runtime
                )
            self.assertEqual(
                read_embedded_app(res.output_path),
                EmbeddedApp(name="good.pl", source='say "fresh"\n'),
            )
            self.assertEqual(strip_existing_trailer(res.output_path.read_bytes()), raw_host)


if __name__ == "__main__":
    unittest.main()
