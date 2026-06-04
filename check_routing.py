"""
Smoke test for custom output-file routing.

Exercises the `route` + `files` API: splitting one module's objects across files by kind, merging objects from
multiple modules into one file, excluding objects, custom file titles and YAML front matter, and correct cross-file
and same-file link computation.
"""

import enum
import shutil
import tempfile
from dataclasses import is_dataclass
from pathlib import Path

import sample.enumeration
import sample.example
from markdown_doc.generator import (
    FileMeta,
    MarkdownAnchorStyle,
    MarkdownGenerator,
    MarkdownOptions,
)

DATA = "dataset-data"
ENUMS = "dataset-enums"
REST = "dataset-rest"


def route(obj: object) -> str | None:
    "Routes sample objects: enums into one file, data-classes into another, everything else into a third."

    name = getattr(obj, "__name__", "")
    if name == "Skipped":
        return None  # exclusion via routing
    if isinstance(obj, type) and issubclass(obj, enum.Enum):
        return ENUMS
    if is_dataclass(obj):
        return DATA
    return REST


FILES = {
    DATA: FileMeta("data/tables.md", title="Data Classes", front_matter={"description": "Sample data-classes."}),
    ENUMS: FileMeta("enums.md", title="Enumerations", front_matter={"description": "Sample enumerations: kind = a/b."}),
    REST: FileMeta("rest.md", title="Other Definitions"),
}


def check_basic_routing() -> None:
    "Split/merge routing, exclusion, front matter, custom titles, and cross-file vs same-file links."

    out_dir = Path(tempfile.mkdtemp(prefix="markdown_doc_routing_"))
    try:
        MarkdownGenerator(
            [sample.example, sample.enumeration],
            options=MarkdownOptions(anchor_style=MarkdownAnchorStyle.GITBOOK, include_private=True, stdlib_links=True),
            route=route,
            files=FILES,
        ).generate(out_dir)

        tables = (out_dir / "data" / "tables.md").read_text(encoding="utf-8")
        enums = (out_dir / "enums.md").read_text(encoding="utf-8")
        rest = (out_dir / "rest.md").read_text(encoding="utf-8")

        # front matter and custom title are emitted at the top of a routed file
        assert tables.startswith("---\ndescription: Sample data-classes.\n---\n"), "missing/incorrect front matter"
        assert "# Data Classes {#dataset-data}" in tables, "missing custom H1 title with anchor"

        # a value with a YAML-significant ': ' is quoted
        assert 'description: "Sample enumerations: kind = a/b."' in enums, "front-matter value not YAML-quoted"

        # the excluded class does not appear anywhere
        for content in (tables, enums, rest):
            assert "Skipped" not in content, "excluded object leaked into output"

        # a routed file with no front matter still gets a title
        assert rest.startswith("\n# Other Definitions {#dataset-rest}") or rest.startswith("# Other Definitions"), "missing title in rest.md"

        # cross-file link: SampleClass (data file) references types; links to enums must point at enums.md from data/tables.md
        # the relative path from data/tables.md to enums.md is ../enums.md
        assert "../enums.md#" in tables, "expected cross-file link to ../enums.md in data/tables.md"

        # same-file link: a data-class referencing another data-class links locally (no file prefix)
        assert "](#sample.example.SampleClass)" in tables or "](#sample.example." in tables, "expected a local same-file anchor link in data/tables.md"

        print("=== BASIC ROUTING CHECKS PASSED ===")
        print(f"  data/tables.md: {len(tables)} bytes")
        print(f"  enums.md:       {len(enums)} bytes")
        print(f"  rest.md:        {len(rest)} bytes")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


MERGED = "dataset-merged"


def route_sectioned(obj: object) -> "str | tuple[str, str] | None":
    "Routes data-classes and enums into one merged file, in separate ordered sections; excludes everything else."

    if isinstance(obj, type) and issubclass(obj, enum.Enum):
        return (MERGED, "enums")
    if is_dataclass(obj):
        return (MERGED, "dataclasses")
    return None


def check_section_ordering() -> None:
    "A merged file with `section_order` emits sections in declared order, single H1, no sub-heading, links intact."

    out_dir = Path(tempfile.mkdtemp(prefix="markdown_doc_sections_"))
    try:
        files = {
            MERGED: FileMeta(
                "merged.md",
                title="Merged",
                front_matter={"description": "Data-classes then enums."},
                section_order=["dataclasses", "enums"],
            )
        }
        MarkdownGenerator(
            [sample.example],
            options=MarkdownOptions(anchor_style=MarkdownAnchorStyle.GITBOOK, include_private=True, stdlib_links=True),
            route=route_sectioned,
            files=files,
        ).generate(out_dir)

        merged = (out_dir / "merged.md").read_text(encoding="utf-8")

        # exactly one H1 in the file
        h1_count = sum(1 for line in merged.splitlines() if line.startswith("# "))
        assert h1_count == 1, f"expected exactly one H1, found {h1_count}"

        # the declared section order places a representative data-class before a representative enum
        dataclass_pos = merged.find("{#sample.example.SampleClass}")
        enum_pos = merged.find("{#sample.example.EnumType}")
        assert dataclass_pos != -1 and enum_pos != -1, "expected both a data-class and an enum in the merged file"
        assert dataclass_pos < enum_pos, "section_order not honored: data-classes should precede enums"

        # no spurious section sub-heading was emitted (sections are ordering-only)
        assert "## dataclasses" not in merged and "## enums" not in merged, "unexpected section sub-heading emitted"

        # same-file link between objects in different sections of the same file is a local anchor (no file prefix)
        assert "](#sample.example." in merged, "expected same-file local anchor link within merged file"
        assert "](merged.md#" not in merged, "same-file link should not include the file name"

        print("=== SECTION ORDERING CHECKS PASSED ===")
        print(f"  merged.md: {len(merged)} bytes (data-classes before enums, single H1)")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def main() -> None:
    check_basic_routing()
    check_section_ordering()


if __name__ == "__main__":
    main()
