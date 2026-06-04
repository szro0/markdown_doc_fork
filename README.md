# Generate Markdown documentation from Python code

This library generates Markdown documentation directly from Python code, utilizing Python type annotations.

## Features at a glance

* Each module produces a Markdown file.
* [Documentation strings](https://docs.python.org/3/library/stdtypes.html#definition.__doc__) are extracted from module, class, enumeration and function definitions.
* Cross-references may be local or fully qualified, and work across modules.
* Classes with member variable declarations produce member documentation.
* Data-class field descriptions are validated if they have a matching member variable declaration.
* Enumeration members are published, even if they lack a description.
* Magic methods (e.g. `__eq__`) are published if they have a doc-string.
* Multi-line code blocks in doc-strings are retained as Markdown code blocks.
* Forward-references and type annotations as strings are automatically evaluated.

## Documentation features

Cross-references with Sphinx-style syntax are supported in module, class and function doc-strings:

```python
@dataclass
class SampleClass:
    """
    This class is extended by :class:`DerivedClass`.

    This class implements :meth:`__lt__` and :meth:`SampleClass.__gt__`.
    """
```

The following Sphinx-style cross-references are recognized:

* `:mod:` for a module
* `:class:` for a regular class
* `:exc:` for an exception class
* `:deco:` for a decorator function
* `:func:` for a function defined at the module level
* `:meth:` for a method of a class

Class member variable and data-class field descriptions are defined with `:param ...:`:

```python
@dataclass
class DerivedClass(SampleClass):
    """
    This data-class derives from another base class.

    :param union: A union of several types.
    :param json: A complex type with type substitution.
    :param schema: A complex type without type substitution.
    """

    union: SimpleType
    json: JsonType
    schema: Schema
```

Enumeration member description follows the member value assignment:

```python
class EnumType(enum.Enum):
    enabled = "enabled"
    "Documents the enumeration member `enabled`."

    disabled = "disabled"
    "Documents the enumeration member `disabled`."
```

## Usage

### Calling the utility in Python

```python
from markdown_doc.generator import MarkdownGenerator

MarkdownGenerator([module1, module2, module3]).generate(out_dir)
```

Pass an object of `MarkdownOptions` to configure behavior:

```python
MarkdownGenerator(
    [module1, module2, module3],
    options=MarkdownOptions(
        anchor_style=MarkdownAnchorStyle.GITBOOK,
        partition_strategy=PartitionStrategy.SINGLE,
        include_private=False,
        stdlib_links=True,
    ),
).generate(out_dir)
```

### Custom output routing

By default, one Markdown file is written per module (or per module and kind with `PartitionStrategy.BY_KIND`), and the file system layout mirrors the Python module hierarchy. If you need full control over which objects end up in which file — for example to group objects across module boundaries, to split a single module into several files, or to publish to a documentation system that expects specific file names — pass a `route` callable and a `files` registry.

The `route` callable maps each documented object (class, data-class, enumeration, module-level function or `NewType`) to an opaque output-file key, or to `None` to exclude it from the output entirely. Objects sharing a key are written into the same file, even if they come from different modules. The `files` registry maps each key to a `FileMeta` describing the output file name, its heading title and an optional YAML front-matter block. Cross-references between objects are resolved against this routing, so links always point at the correct file.

```python
from markdown_doc.generator import FileMeta, MarkdownGenerator, MarkdownOptions

def route(obj: object) -> str | None:
    if getattr(obj, "__name__", "") in EXCLUDED:
        return None  # exclude this object from the output
    module = obj.__module__.rsplit(".", 1)[-1]
    if module == "canvas":
        # split one module into two files based on a domain predicate
        return "dataset-canvas" if is_table(obj) else "dataset-canvas-types"
    # merge other modules each into a single file
    return f"dataset-{module}"

files = {
    "dataset-canvas": FileMeta(
        "dataset-canvas.md",
        title="Tables in canvas namespace",
        front_matter={"description": "Tables in the canvas namespace."},
    ),
    "dataset-canvas-types": FileMeta("dataset-canvas-types.md", title="Types in canvas namespace"),
    # ...
}

MarkdownGenerator(
    [module1, module2, module3],
    options=MarkdownOptions(anchor_style=MarkdownAnchorStyle.GITBOOK),
    route=route,
    files=files,
).generate(out_dir)
```

When `route` is given, `partition_strategy` is ignored. A key with no entry in `files` falls back to a file named `<key>.md` with the key as its heading. Custom routing is available through the Python API only; it is not exposed on the command line.

#### Ordering objects within a file

When several kinds of objects are routed into one file, you can control the order they are emitted in by returning a `(file_key, section_key)` pair from `route` instead of a bare key, and declaring the section order in `FileMeta.section_order`:

```python
def route(obj: object) -> str | tuple[str, str] | None:
    module = obj.__module__.rsplit(".", 1)[-1]
    # merge tables and types into one file, but keep tables first
    return (f"dataset-{module}", "tables" if is_table(obj) else "types")

files = {
    "dataset-logs": FileMeta(
        "dataset-logs.md",
        title="Logs",
        section_order=["tables", "types"],  # tables emitted before types
    ),
}
```

Sections only affect emission order — no sub-heading or separator is emitted between them, and the file still has a single heading. Objects in sections not listed in `section_order` are emitted after the listed ones, in discovery order. A bare-key return (no section) behaves as before.

### Running the utility from the command line

```
$ python3 -m markdown_doc --help
usage: markdown_doc [-h] [-d [DIRECTORY ...]] [-m [MODULE ...]] [-r ROOT_DIR] [-o OUT_DIR] [--anchor-style {GitBook,GitHub}] [--partition {single,by_kind}]

Generates Markdown documentation from Python code

options:
  -h, --help            show this help message and exit
  -d [DIRECTORY ...], --directory [DIRECTORY ...]
                        folder(s) to recurse into when looking for modules
  -m [MODULE ...], --module [MODULE ...]
                        qualified names(s) of Python module(s) to scan
  -r ROOT_DIR, --root-dir ROOT_DIR
                        path to act as root for converting directory paths into qualified module names (default: working directory)
  -o OUT_DIR, --out-dir OUT_DIR
                        output directory (default: 'docs' in working directory)
  --anchor-style {GitBook,GitHub}
                        output format for generating anchors in headings
  --partition {single,by_kind}
                        how to split module contents across Markdown files
```

## Related work

In order to reduce added complexity, this library does not use the Sphinx framework with [autodoc](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html).
