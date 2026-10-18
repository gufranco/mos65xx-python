from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conformance.family_member import ROOT

TRANSLATIONS = ("README.ja.md", "README.zh-Hans.md", "README.zh-HK.md")


READMES = ("README.md", *TRANSLATIONS)


FENCE = re.compile(r"^```.*?^```$", re.M | re.S)


LINK = re.compile(r"\]\(([^)\s]+)\)")


UNDER_TAGLINE = re.compile(r"^# .+\n\n(?:.+\n)+\n(.+)$", re.M)


def fenced(text: str) -> list[str]:
    return FENCE.findall(text)


def heading_levels(text: str) -> list[int]:
    return [len(marks) for marks in re.findall(r"^(#{1,6}) ", FENCE.sub("", text), re.M)]


def switcher(text: str) -> str:
    found = UNDER_TAGLINE.search(FENCE.sub("", text))
    return found.group(1) if found else ""


def body_links(text: str) -> list[str]:
    unfenced = FENCE.sub("", text)
    return sorted(LINK.findall(unfenced.replace(switcher(text), "", 1)))


def switcher_gaps(name: str, text: str) -> list[str]:
    linked = set(LINK.findall(switcher(text)))
    others = [one for one in READMES if one != name]
    return [one for one in others if one not in linked] + [name] * (name in linked)


class TranslatedTest(unittest.TestCase):
    def english(self) -> str:
        return (ROOT / "README.md").read_text()

    def translated(self) -> dict[str, str]:
        return {name: (ROOT / name).read_text() for name in TRANSLATIONS if (ROOT / name).is_file()}

    def test_every_translation_is_there(self) -> None:
        # Arrange
        expected = list(TRANSLATIONS)

        # Act
        held = sorted(self.translated())

        # Assert
        self.assertEqual(held, sorted(expected))

    def test_every_readme_links_the_other_three_under_its_tagline(self) -> None:
        # Arrange
        held = {"README.md": self.english(), **self.translated()}

        # Act
        gaps = {name: switcher_gaps(name, text) for name, text in held.items()}

        # Assert
        self.assertEqual({name: gap for name, gap in gaps.items() if gap}, {})

    def test_every_translation_keeps_the_english_headings_level_by_level(self) -> None:
        # Arrange
        expected = heading_levels(self.english())

        # Act
        held = {name: heading_levels(text) for name, text in self.translated().items()}

        # Assert
        self.assertEqual({name: levels for name, levels in held.items() if levels != expected}, {})

    def test_every_translation_carries_the_english_code_byte_for_byte(self) -> None:
        # Arrange
        expected = fenced(self.english())

        # Act
        held = {name: fenced(text) for name, text in self.translated().items()}

        # Assert
        self.assertEqual([name for name, code in held.items() if code != expected], [])

    def test_every_translation_links_where_the_english_links(self) -> None:
        # Arrange
        expected = body_links(self.english())

        # Act
        held = {name: body_links(text) for name, text in self.translated().items()}

        # Assert
        self.assertEqual([name for name, links in held.items() if links != expected], [])

    def test_a_heading_inside_a_code_block_is_not_counted(self) -> None:
        # Arrange
        text = "# Title\n\n```bash\n# not a heading\n```\n\n## Part\n"

        # Act
        levels = heading_levels(text)

        # Assert
        self.assertEqual(levels, [1, 2])

    def test_a_switcher_that_links_to_itself_is_reported(self) -> None:
        # Arrange
        text = (
            "# Title\n\nWhat it is.\n\n"
            "[English](README.md) | [日本語](README.ja.md) | 简体中文 | [HK](README.zh-HK.md)\n"
        )

        # Act
        gaps = switcher_gaps("README.ja.md", text)

        # Assert
        self.assertEqual(gaps, ["README.zh-Hans.md", "README.ja.md"])

    def test_a_switcher_above_the_title_is_reported_missing(self) -> None:
        # Arrange
        text = (
            "[日本語](README.ja.md) | [简体中文](README.zh-Hans.md) | [HK](README.zh-HK.md)\n\n"
            "# Title\n\nWhat it is.\n\nBody.\n"
        )

        # Act
        gaps = switcher_gaps("README.md", text)

        # Assert
        self.assertEqual(gaps, ["README.ja.md", "README.zh-Hans.md", "README.zh-HK.md"])

    def test_a_readme_with_no_title_carries_no_switcher(self) -> None:
        # Arrange
        text = "[日本語](README.ja.md)\n\nBody.\n"

        # Act
        found = switcher(text)

        # Assert
        self.assertEqual(found, "")

    def test_the_switcher_line_is_not_compared_as_a_body_link(self) -> None:
        # Arrange
        text = "# Title\n\nWhat it is.\n\n[日本語](README.ja.md)\n\nSee [LICENSE](LICENSE).\n"

        # Act
        links = body_links(text)

        # Assert
        self.assertEqual(links, ["LICENSE"])


ANCHOR = re.compile(r'<a id="([^"]+)"></a>')


def slug(title: str) -> str:
    lowered = re.sub(r"[`*_\[\]()]", "", title).strip().lower()
    return re.sub(r"[^\w\- ]", "", lowered).replace(" ", "-")


def landings(text: str) -> set[str]:
    unfenced = FENCE.sub("", text)
    titled = {slug(title) for title in re.findall(r"^#{1,6} (.+)$", unfenced, re.M)}
    return titled | set(ANCHOR.findall(unfenced))


def in_page_links(text: str) -> set[str]:
    return set(re.findall(r"\]\(#([^)\s]+)\)", FENCE.sub("", text)))


class InPageLinkTest(unittest.TestCase):
    def test_every_in_page_link_in_every_readme_lands(self) -> None:
        # Arrange
        held = {name: (ROOT / name).read_text() for name in READMES if (ROOT / name).is_file()}

        # Act
        stray = {name: sorted(in_page_links(text) - landings(text)) for name, text in held.items()}

        # Assert
        self.assertEqual({name: links for name, links in stray.items() if links}, {})

    def test_a_translated_heading_lands_through_an_anchor(self) -> None:
        # Arrange
        text = '<a id="models"></a>\n\n## モデル\n\nSee [the models](#models).\n'

        # Act
        stray = in_page_links(text) - landings(text)

        # Assert
        self.assertEqual(stray, set())


if __name__ == "__main__":
    unittest.main()
