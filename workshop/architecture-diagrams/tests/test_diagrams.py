from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "sources"
RENDERER = ROOT / "render.py"
GENERATED_DIR = ROOT / "generated-assets"

DIAGRAMS = (
    "pellier-deployed-topology",
    "lab-2-marco-grounding",
    "lab-1-anna-retrieval",
    "lab-3-theo-managed-path",
    "lab-4-jessica-governance",
    "lab-4-deny-allow-sequence",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DiagramSourceTests(unittest.TestCase):
    def test_manifest_has_six_graphviz_sources(self) -> None:
        self.assertEqual(
            sorted(path.stem for path in SOURCE_DIR.glob("*.dot")),
            sorted(DIAGRAMS),
        )

    def test_every_source_is_valid_graphviz(self) -> None:
        for stem in DIAGRAMS:
            with self.subTest(diagram=stem):
                subprocess.run(
                    ["dot", "-Tsvg", str(SOURCE_DIR / f"{stem}.dot")],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

    def test_deployed_topology_has_numbered_path_and_four_write_points(self) -> None:
        source = (SOURCE_DIR / "pellier-deployed-topology.dot").read_text()
        for step in range(1, 9):
            self.assertIn(f"{step:02d} ·", source)
        for write_point in range(1, 5):
            self.assertIn(f"E{write_point} ·", source)
            self.assertIn(f"WRITE E{write_point}", source)

    def test_lab_overlays_name_persona_and_primary_boundary(self) -> None:
        expected = {
            "lab-2-marco-grounding": ("MARCO", "tool_audit", "NOT CLAIMED"),
            "lab-1-anna-retrieval": ("ANNA", "RRF", "retrieval_receipts"),
            "lab-3-theo-managed-path": ("THEO", "AGENTCORE MEMORY", "OTEL"),
            "lab-4-jessica-governance": ("JESSICA", "CEDAR", "POSTGRESQL RLS"),
        }
        for stem, fragments in expected.items():
            source = (SOURCE_DIR / f"{stem}.dot").read_text()
            with self.subTest(diagram=stem):
                for fragment in fragments:
                    self.assertIn(fragment, source)

    def test_lab4_sequence_keeps_deny_and_allow_as_separate_lanes(self) -> None:
        source = (SOURCE_DIR / "lab-4-deny-allow-sequence.dot").read_text()
        for fragment in (
            "DENY LANE",
            "ALLOW LANE",
            "NOT INVOKED",
            "0 tool_audit",
            "exactly 1 execution",
            "Aurora RLS".upper(),
            "human review is not implied",
        ):
            self.assertIn(fragment, source)


class DiagramRendererTests(unittest.TestCase):
    def _render(self, output_dir: Path) -> None:
        subprocess.run(
            [sys.executable, str(RENDERER), "--output-dir", str(output_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_renderer_emits_svg_and_png_for_every_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            self._render(output_dir)
            for stem in DIAGRAMS:
                self.assertTrue((output_dir / f"{stem}.svg").is_file())
                self.assertTrue((output_dir / f"{stem}.png").is_file())
                self.assertIn(
                    b"<svg", (output_dir / f"{stem}.svg").read_bytes()
                )
                self.assertEqual(
                    (output_dir / f"{stem}.png").read_bytes()[:8],
                    b"\x89PNG\r\n\x1a\n",
                )

    def test_two_renders_are_byte_for_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir = Path(first)
            second_dir = Path(second)
            self._render(first_dir)
            self._render(second_dir)
            for stem in DIAGRAMS:
                for suffix in ("svg", "png"):
                    name = f"{stem}.{suffix}"
                    with self.subTest(asset=name):
                        self.assertEqual(
                            digest(first_dir / name),
                            digest(second_dir / name),
                        )

    def test_checked_in_assets_match_sources(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RENDERER),
                "--output-dir",
                str(GENERATED_DIR),
                "--check",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
