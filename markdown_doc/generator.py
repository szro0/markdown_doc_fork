"""
Generate Markdown documentation from Python code

Copyright 2024-2026, Levente Hunyadi

:see: https://github.com/hunyadi/markdown_doc
"""

import enum
import inspect
import logging
import os
import re
import sys
import typing
from dataclasses import dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from types import FunctionType, MethodType, ModuleType
from typing import Any, Callable, Mapping, NewType, TypeGuard

from docsource.docstring import DocstringSeeAlso, check_docstring, parse_type
from docsource.enumeration import enum_labels
from docsource.inspection import get_module_classes, get_module_functions, is_type_enum

from .formatter import TypeFormatter, TypeFormatterOptions
from .resolver import ClassResolver, MemberFunctionResolver, MemberResolver, ModuleFunctionResolver, ModuleResolver, Resolver


def replace_links(text: str) -> str:
    """
    Replaces plain text URLs with Markdown links.

    :param text: String with possible occurrences of URLs.
    :returns: String with replacements made.
    """

    regex = re.compile(
        r"""
        \b
        (                                  # Capture 1: entire matched URL
        (?:
            https?:                        # URL protocol and colon
            (?:
            /{1,3}                         # 1-3 slashes
            |                              #   or
            [a-z0-9%]                      # Single letter or digit or '%'
                                           # (Trying not to match e.g. "URI::Escape")
            )
            |                              #   or
                                           # looks like domain name followed by a slash:
            [a-z0-9.\-]+[.]
            (?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|
            ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|
            by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|
            eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|
            im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|
            md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|
            pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|sk|sl|sm|sn|so|sr|ss|st|
            su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|
            wf|ws|ye|yt|yu|za|zm|zw)
            /
        )
        [^\s()<>{}\[\]]*                   # 0+ non-space, non-()<>{}[]
        (?:                                # 0+ times:
            \(                             #   Balanced parens containing:
            [^\s()]*                       #   0+ non-paren chars
            (?:                            #   0+ times:
            \([^\s()]*\)                   #     Inner balanced parens containing 0+ non-paren chars
            [^\s()]*                       #     0+ non-paren chars
            )*
            \)
            [^\s()<>{}\[\]]*               # 0+ non-space, non-()<>{}[]
        )*
        (?:                                # End with:
            \(                             #   Balanced parens containing:
            [^\s()]*                       #   0+ non-paren chars
            (?:                            #   0+ times:
            \([^\s()]*\)                   #     Inner balanced parens containing 0+ non-paren chars
            [^\s()]*                       #     0+ non-paren chars
            )*
            \)
            |                              #   or
            [^\s`!()\[\]{};:'".,<>?«»“”‘’] # not a space or one of these punctuation chars
        )
        |					# OR, the following to match naked domains:
        (?:
            (?<!@)			# not preceded by a @, avoid matching foo@_gmail.com_
            [a-z0-9]+
            (?:[.\-][a-z0-9]+)*
            [.]
            (?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|
            ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|
            by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|
            eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|
            im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|
            md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|
            pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|sk|sl|sm|sn|so|sr|ss|st|
            su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|
            wf|ws|ye|yt|yu|za|zm|zw)
            \b
            /?
            (?!@)			# not succeeded by a @, avoid matching "foo.na" in "foo.na@example.com"
        )
        )
        """,
        re.VERBOSE | re.UNICODE,
    )
    text, count = regex.subn(r"[\1](\1)", text)
    logging.debug("%d URL(s) found", count)
    return text


def quote_value(value: Any) -> str:
    "Renders a value as Markdown preformatted text."

    s = repr(value)
    if "`" not in s:
        return f"`{s}`"
    elif "``" not in s:
        return f"``{s}``"
    else:
        return f"```{s}```"


def _yaml_scalar(s: str) -> str:
    """
    Renders a string as a YAML scalar, double-quoting it if it contains characters that are significant in YAML flow
    context or would otherwise be misinterpreted (e.g. a leading indicator character, a `: ` or ` #` sequence).
    """

    if s == "":
        return '""'
    needs_quotes = (
        s != s.strip() or ": " in s or " #" in s or s[0] in "!&*?|>%@`\"'#,[]{}:-" or s.lower() in ("true", "false", "null", "yes", "no", "on", "off", "~")
    )
    if not needs_quotes:
        return s
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def type_name(tp: NewType | type[Any]) -> str:
    return tp.__name__  # type: ignore[union-attr]


def safe_name(name: str) -> str:
    "Object name with those characters escaped that are allowed in Python identifiers but have special meaning in Markdown."

    regex = re.compile(r"(\b_+|_+\b)")
    return regex.sub(lambda m: m.group(0).replace("_", "\\_"), name)


def _safe_id_part(part: str) -> str:
    if part.startswith("__"):
        return f"sp{part}"  # special member variable or function
    elif part.startswith("_"):
        return f"p{part}"  # private member variable or function
    else:
        return part


def safe_id(name: str) -> str:
    """
    Object identifier that qualifies as a Markdown anchor.

    The generated identifier is used as an anchor for Markdown links.

    Usually, the identifier matches the class or function name. However, objects with private visibility have a name
    that begins with `_`, and the name of special methods starts with `__`, both of which confuses many Markdown
    formatting engines. We take a safe approach to prefix these with `p` and `sp`, respectively.
    """

    parts = name.split(".")
    return ".".join(_safe_id_part(part) for part in parts)


def module_path(target: str, source: str) -> str:
    """
    Returns a relative path from source to target.

    :param target: The fully qualified name of the module to link to (in dot notation).
    :param source: The fully qualified name of the module to link from (in dot notation).
    """

    target_path = Path("/" + target.replace(".", "/") + ".md")
    source_path = Path("/" + source.replace(".", "/") + ".md")
    target_dir = target_path.parent
    source_dir = source_path.parent
    if sys.version_info >= (3, 12):
        relative_path = Path(target_dir).relative_to(source_dir, walk_up=True)
    else:
        relative_path = Path(os.path.relpath(target_dir, start=source_dir))
    return (relative_path / target_path.name).as_posix()


def _relative_md_path(target: str, source: str) -> str:
    """
    Returns a relative path from one output file to another, given their on-disk file names.

    Unlike :func:`module_path`, which derives a file system path from a dotted module name, this function operates on
    arbitrary output file names (as supplied via a routing file-metadata registry), which may themselves contain
    POSIX-style subdirectories.

    :param target: The output file name to link to (POSIX-style, relative to the target directory).
    :param source: The output file name to link from (POSIX-style, relative to the target directory).
    """

    target_path = Path("/" + target)
    source_path = Path("/" + source)
    target_dir = target_path.parent
    source_dir = source_path.parent
    if sys.version_info >= (3, 12):
        relative_path = Path(target_dir).relative_to(source_dir, walk_up=True)
    else:
        relative_path = Path(os.path.relpath(target_dir, start=source_dir))
    return (relative_path / target_path.name).as_posix()


def get_module_new_types(module: ModuleType) -> list[NewType]:
    """
    Returns all new types declared directly in a module.

    :param module: The module to scan.
    :returns: `NewType` instances declared in the specified module.
    """

    def is_type_member(member: object) -> TypeGuard[NewType]:
        return isinstance(member, NewType) and member.__module__ == module.__name__

    return [class_type for _, class_type in inspect.getmembers(module, is_type_member)]


CallableType = Callable[..., Any]


def is_function(fn: Any) -> TypeGuard[CallableType]:
    "Identifies module-level functions, class member functions, functions with `@classmethod` and `@staticmethod`."

    return isinstance(fn, FunctionType) or isinstance(fn, MethodType) or isinstance(fn, classmethod) or isinstance(fn, staticmethod)


@enum.unique
class ObjectKind(enum.Enum):
    "Represents a group of Python types, e.g. regular classes, data-classes, enumerations, module-level functions, etc."

    CLASS = "class"
    "Group for regular classes."

    DATACLASS = "dataclass"
    "Group for data-classes."

    ENUM = "enum"
    "Group for enumerations."

    FUNCTION = "function"
    "Group for module-level functions."

    MODULE = "module"
    "Group for modules."


ObjectType = type | CallableType


def object_kind(cls: ObjectType | ModuleType) -> ObjectKind:
    "Determines the group of types that the passed type belongs to."

    if isinstance(cls, ModuleType):
        return ObjectKind.MODULE
    elif isinstance(cls, FunctionType):  # module-level function
        return ObjectKind.FUNCTION
    elif is_type_enum(cls):
        return ObjectKind.ENUM
    elif is_dataclass(cls):
        return ObjectKind.DATACLASS
    else:
        return ObjectKind.CLASS


RouteKey = str
"Opaque key identifying a routed output file. Multiple objects (possibly from different modules) sharing a key are emitted into the same file."

SectionKey = str
"Opaque key identifying an ordered section within a routed output file. Section order is set via `FileMeta.section_order`."

RoutedKey = RouteKey | tuple[RouteKey, SectionKey]
"Routing callable result: an output file key, or a (file key, section key) pair to also place the object in a section."

RouteFn = Callable[[ObjectType], RoutedKey | None]
"Maps a documented object to a routed output file key (optionally with a section key), or `None` to exclude the object from output."


def _split_routed_key(routed: RoutedKey) -> tuple[RouteKey, SectionKey | None]:
    "Normalizes a routing callable's return value into a (file key, section key) pair; a bare key has no section."

    if isinstance(routed, tuple):
        return routed
    return (routed, None)


@dataclass
class FileMeta:
    """
    Metadata describing a routed output file.

    :param filename: Output file name relative to the target directory, e.g. `dataset-canvas.md`. May contain
        POSIX-style subdirectories, which are created on demand. Must not be absolute or contain `..` segments.
    :param title: Heading (H1) text for the file. Defaults to the routing key if omitted.
    :param front_matter: Key/value pairs emitted as a leading YAML front-matter block, before the heading.
    :param section_order: Order in which sections (identified by the section key returned by the routing callable)
        are emitted within this file. Objects in sections not listed here follow the listed ones, in discovery order.
        Sections only affect ordering; no sub-heading or separator is emitted between them.
    """

    filename: str
    title: str | None = None
    front_matter: dict[str, str] = field(default_factory=dict[str, str])
    section_order: list[SectionKey] | None = None


FileMetaProvider = "Mapping[RouteKey, FileMeta] | Callable[[RouteKey], FileMeta | None]"
"Supplies metadata for routed output files, either as a mapping keyed by routing key, or as a callable."


@dataclass
class Section:
    """
    A group of documented objects within a single output file, emitted together.

    :param key: The section key (or `None` for objects routed without an explicit section).
    :param new_types: `NewType` aliases in this section, in discovery order.
    :param classes: Classes, data-classes and enumerations in this section, in discovery order.
    :param functions: Module-level functions in this section, in discovery order.
    """

    key: SectionKey | None
    new_types: list[NewType] = field(default_factory=list)
    classes: list[type] = field(default_factory=list)
    functions: list[FunctionType] = field(default_factory=list)


@dataclass
class Bucket:
    """
    A group of documented objects routed to a single output file.

    :param key: The routing key identifying the output file this bucket is emitted to.
    :param sections: Sections within the file, keyed by section key (`None` for the default section),
        in discovery order.
    """

    key: RouteKey
    sections: dict[SectionKey | None, Section] = field(default_factory=dict[SectionKey | None, Section])

    def section_for(self, section_key: SectionKey | None) -> Section:
        "Returns the section for the given key, creating it (in discovery order) on first use."

        section = self.sections.get(section_key)
        if section is None:
            section = Section(section_key)
            self.sections[section_key] = section
        return section


@dataclass
class Context:
    """
    Represents a group of types that are exported as a unit.

    :param module: The module in which the types are defined.
    :param partition: Identifies the group of types.
    :param router: When set, file identity is derived from routing keys rather than module name and partition.
    """

    module: ModuleType
    partition: ObjectKind | None
    router: "Router | None" = None

    def name(self) -> str:
        if self.router is not None:
            return self.router.current_key
        if self.partition is not None:
            return f"{self.module.__name__}-{self.partition.value}"
        else:
            return self.module.__name__

    def matches(self, cls: ObjectType) -> bool:
        if self.router is not None:
            return self.router.key_of(cls) == self.router.current_key
        if cls.__module__ != self.module.__name__:
            return False
        if self.partition is None:
            return True

        return self.partition is object_kind(cls)

    def path_to(self, cls: ObjectType | ModuleType) -> str:
        if self.router is not None:
            target = self.router.filename_of(cls)
            source = self.router.filename_of_key(self.router.current_key)
            return _relative_md_path(target, source)

        if self.partition is not None:
            kind = object_kind(cls)
        else:
            kind = None

        if isinstance(cls, ModuleType):
            module = cls
        else:
            module = sys.modules[cls.__module__]

        target = Context(module, kind).name()
        source = self.name()
        return module_path(target, source)


def _object_route_id(cls: NewType | ObjectType | ModuleType) -> tuple[str, str]:
    "Stable identity for a documented object, used to look up its routed output file."

    if isinstance(cls, ModuleType):
        return (cls.__name__, "")
    elif isinstance(cls, NewType):
        return (cls.__module__, type_name(cls))
    else:
        return (cls.__module__, getattr(cls, "__qualname__", cls.__name__))


class Router:
    """
    Resolves which routed output file each documented object belongs to.

    The router owns the global bucket map (built in a first pass over all modules) and the file-metadata registry,
    and is the single source of truth for cross-file link computation. The ``current_key`` attribute identifies the
    file currently being written; it is updated as each bucket is emitted.
    """

    current_key: RouteKey

    def __init__(
        self,
        buckets: dict[RouteKey, Bucket],
        file_meta: Callable[[RouteKey], FileMeta | None],
        object_keys: dict[tuple[str, str], RouteKey],
        module_keys: dict[str, RouteKey],
    ) -> None:
        self._buckets = buckets
        self._file_meta = file_meta
        self._object_keys = object_keys
        self._module_keys = module_keys
        self.current_key = ""

    def key_of(self, cls: NewType | ObjectType | ModuleType) -> RouteKey | None:
        "Routing key of the output file that contains the given object, or `None` if it is not part of the output."

        if isinstance(cls, ModuleType):
            # modules do not route directly; map a module reference to a bucket it contributes to (if any)
            return self._module_keys.get(cls.__name__)
        return self._object_keys.get(_object_route_id(cls))

    def filename_of_key(self, key: RouteKey) -> str:
        "On-disk file name for a routing key, falling back to `<key>.md` when the key has no registry entry."

        meta = self._file_meta(key)
        if meta is not None and meta.filename:
            return meta.filename
        return f"{key}.md"

    def filename_of(self, cls: ObjectType | ModuleType) -> str:
        "On-disk file name of the output file that contains the given object."

        key = self.key_of(cls)
        if key is None:
            raise KeyError(f"object is not part of the routed output: {cls!r}")
        return self.filename_of_key(key)


def module_anchor(module: ModuleType) -> str:
    "Module anchor within a Markdown file."

    assert isinstance(module, ModuleType), f"expected: module reference; got: {type(module).__name__}"
    return safe_id(module.__name__)


def module_link(module: ModuleType, context: Context) -> str:
    "Markdown link with a fully-qualified module reference."

    assert isinstance(module, ModuleType), f"expected: module reference; got: {type(module).__name__}"
    return f"[{module.__name__}]({context.path_to(module)}#{safe_id(module.__name__)})"


def class_anchor(cls: type) -> str:
    "Class anchor within a Markdown file."

    assert not isinstance(cls, ModuleType) and not is_function(cls), f"expected: class reference; got: {type(cls).__name__}"  # type: ignore[unreachable]
    return safe_id(f"{cls.__module__}.{cls.__qualname__}")


def new_type_anchor(cls: NewType) -> str:
    "New type anchor within a Markdown file."

    return safe_id(f"{cls.__module__}.{type_name(cls)}")


def _class_link(cls: ObjectType, context: Context, text: str | None = None) -> str:
    "Markdown link with a partially- or fully-qualified class or function reference."

    qualname = f"{cls.__module__}.{cls.__qualname__}"
    local_link = f"#{safe_id(qualname)}"

    if context.matches(cls):
        # local reference
        link = local_link
    else:
        # non-local reference
        link = f"{context.path_to(cls)}{local_link}"

    if text is None:
        text = cls.__name__
    return f"[{safe_name(text)}]({link})"


def class_link(cls: type, context: Context, text: str | None = None) -> str:
    "Markdown link with a partially- or fully-qualified class reference."

    assert not isinstance(cls, ModuleType) and not is_function(cls), f"expected: class reference; got: {type(cls).__name__}"  # type: ignore[unreachable]
    return _class_link(cls, context, text=text)


def new_type_link(cls: NewType, context: Context, text: str | None = None) -> str:
    "Markdown link with a partially- or fully-qualified new type reference."

    qualname = f"{cls.__module__}.{type_name(cls)}"
    local_link = f"#{safe_id(qualname)}"

    if context.matches(cls):
        # local reference
        link = local_link
    else:
        # non-local reference
        link = f"{context.path_to(cls)}{local_link}"

    if text is None:
        text = type_name(cls)
    return f"[{safe_name(text)}]({link})"


def function_anchor(fn: CallableType) -> str:
    "Function anchor within a Markdown file."

    assert is_function(fn), f"expected: function reference; got: {type(fn).__name__}"
    return safe_id(f"{fn.__module__}.{fn.__qualname__}")


def function_link(fn: CallableType, context: Context) -> str:
    "Markdown link with a partially- or fully-qualified function reference."

    assert is_function(fn), f"expected: function reference; got: {type(fn).__name__}"
    return _class_link(fn, context)


def decorator_link(fn: CallableType, context: Context) -> str:
    "Markdown link with a partially- or fully-qualified decorator function reference."

    assert is_function(fn), f"expected: function reference; got: {type(fn).__name__}"
    return _class_link(fn, context, text=f"@{fn.__name__}")


def _extract_ref(text: str) -> str:
    "Extracts a fully-qualified reference from a reference string possibly with a custom label included."

    regex = re.compile(r"^[^<>]+<([^<>]+)>$")
    if (m := regex.match(text)) is not None:
        # :class:`HTTPAdapter <requests.adapters.HTTPAdapter>`
        return m.group(1)
    else:
        # :class:`HTTPAdapter`
        return text


def is_private(cls: ObjectType) -> bool:
    "True if the class or function is private to the module."

    return cls.__name__.startswith("_") and not cls.__name__.startswith("__")


def is_documented(cls: ObjectType) -> bool:
    "True if the class or function has a doc-string description."

    return parse_type(cls).full_description is not None


class MarkdownWriter:
    "Writes lines to a Markdown document."

    lines: list[str]

    def __init__(self) -> None:
        self.lines = []

    def __bool__(self) -> bool:
        return len(self.lines) > 0

    def fetch(self) -> str:
        lines = "\n".join(self.lines)
        self.lines = []
        return lines

    def print(self, line: str = "") -> None:
        self.lines.append(line)


@enum.unique
class MarkdownAnchorStyle(enum.Enum):
    "Output format for generating anchors in headings."

    GITBOOK = "GitBook"
    'GitBook anchor style, with explicit HTML anchor element <a name="..."></a> in heading text.'

    GITHUB = "GitHub"
    "GitBook anchor style, with Markdown extension syntax {#...} following heading title text."


@enum.unique
class PartitionStrategy(enum.Enum):
    "Determines how to split module contents across Markdown files."

    SINGLE = "single"
    "Create a single Markdown file with all classes, enums and functions in a module."

    BY_KIND = "by_kind"
    "Create separate Markdown files for classes, enums and functions in each module."


@dataclass
class MarkdownOptions:
    """
    Options for generating Markdown output.

    :param anchor_style: Output format for generating anchors in headings.
    :param partition_strategy: Determines how to split module contents across Markdown files.
    :param include_private: Whether to include private classes, functions and methods.
    :param include_undocumented: Whether to include classes, functions and methods without a doc-string description.
    :param stdlib_links: Whether to include references for built-in types and types in the Python standard library.
    :param auxiliary_types: Maps each Python type (typically `Annotated[T, ...]`) to a human-readable name.
    :param route: Maps each documented object to an output file key (or `None` to exclude it). When set, objects are
        grouped into files by this key rather than by module, and `partition_strategy` is ignored. Cross-file links
        are computed from this grouping. The file name, heading and front matter for each key come from the file
        metadata registry passed as `files` to `MarkdownGenerator`.
    :param qualify_cross_module_links: Whether to prefix the text of a link to another object with that object's
        module short-name (e.g. `canvas.users` instead of `users`) when it is defined in a different module than the
        referencing object. Links within the same module keep the short name. The link target is unaffected.
    """

    anchor_style: MarkdownAnchorStyle = MarkdownAnchorStyle.GITHUB
    partition_strategy: PartitionStrategy = PartitionStrategy.SINGLE
    include_private: bool = False
    include_undocumented: bool = False
    stdlib_links: bool = True
    auxiliary_types: dict[object, str] = field(default_factory=dict[object, str])
    route: RouteFn | None = None
    qualify_cross_module_links: bool = False


class ProcessingError(RuntimeError):
    """
    Raised when inspecting a class or function fails.

    :param obj: The class or function object that triggered the error.
    """

    obj: type

    def __init__(self, *args: Any, obj: type) -> None:
        super().__init__(*args)
        self.obj = obj


class MarkdownTypeFormatter:
    "Generates a safe Markdown string from a Python type."

    formatter: TypeFormatter

    def __init__(self, module: ModuleType, type_transform: Callable[[NewType | type[Any]], str], auxiliary_types: dict[object, str]) -> None:
        """
        Creates a type formatter.

        :param module: The module in whose context forward references are evaluated.
        :param type_transform: Transformation to apply to types before a string is emitted, e.g. to create a link in a documentation.
        """

        self.formatter = TypeFormatter(
            context=module, options=TypeFormatterOptions(type_transform=type_transform, value_transform=quote_value, auxiliary_types=auxiliary_types)
        )

    def type_to_markdown(self, data_type: Any) -> str:
        "Emits a safe Markdown string for a data type."

        return self.formatter.python_type_to_str(data_type).replace("[[", "[&#x200B;[").replace("]]", "]&#x200B;]")


class MarkdownGenerator:
    "Generates Markdown documentation for a list of modules."

    modules: list[ModuleType]
    options: MarkdownOptions
    predicate: Callable[[ObjectType], bool] | None
    route: RouteFn | None
    files: Mapping[RouteKey, FileMeta] | Callable[[RouteKey], FileMeta | None] | None
    _router: Router | None

    def __init__(
        self,
        modules: list[ModuleType],
        *,
        options: MarkdownOptions | None = None,
        predicate: Callable[[ObjectType], bool] | None = None,
        route: RouteFn | None = None,
        files: Mapping[RouteKey, FileMeta] | Callable[[RouteKey], FileMeta | None] | None = None,
    ) -> None:
        """
        Instantiates a Markdown generator object.

        :param options: Options for generating Markdown output.
        :param predicate: If given, only those classes and functions are processed for which the predicate returns `True`.
        :param route: Maps each documented object to an output file key (or `None` to exclude it). Overrides
            `options.route` if both are given. When set, objects are grouped into files by key rather than by module,
            and `options.partition_strategy` is ignored.
        :param files: File-metadata registry for routed output, keyed by routing key (a mapping or callable returning
            `FileMeta`). Supplies the file name, heading title and front matter for each routed file.
        """

        self.modules = modules
        self.options = options if options is not None else MarkdownOptions()
        self.predicate = predicate
        self.route = route if route is not None else self.options.route
        self.files = files
        self._router = None

    @property
    def _routing_enabled(self) -> bool:
        return self.route is not None

    def _file_meta(self, key: RouteKey) -> FileMeta | None:
        "Looks up file metadata for a routing key, normalizing the mapping/callable registry forms."

        files = self.files
        if files is None:
            return None
        if callable(files):
            return files(key)
        return files.get(key)

    def _heading_anchor(self, anchor: str, text: str) -> str:
        """
        Creates an anchor in a heading.

        :param anchor: Anchor name, following HTML and Markdown identifier rules.
        :param text: Heading title text.
        """

        match self.options.anchor_style:
            case MarkdownAnchorStyle.GITHUB:
                return f'<a name="{anchor}"></a> {text}'
            case MarkdownAnchorStyle.GITBOOK:
                return text + " {#" + anchor + "}"

    def _is_in_batch(self, obj: ObjectType | ModuleType) -> bool:
        """
        True if a referenced object is part of the generated output, so a link should be emitted to it.

        Without routing this means the object's module is one of the documented modules. With routing it additionally
        requires the object to route to an output file (i.e. it was not excluded by the routing callable returning
        `None`); an excluded object is treated like an external reference and rendered as plain text.
        """

        if isinstance(obj, ModuleType):
            module = obj
        else:
            module = sys.modules[obj.__module__]
        if module not in self.modules:
            return False
        if self._router is not None:
            return self._router.key_of(obj) is not None
        return True

    def _module_link(self, module: ModuleType, context: Context) -> str:
        "Creates a link to a class if it is part of the exported batch."

        if self._is_in_batch(module):
            return module_link(module, context)
        else:
            return safe_name(module.__name__)

    def _link_text(self, obj: NewType | ObjectType, name: str, context: Context) -> str | None:
        """
        Computes custom link text for a reference, or `None` to use the default short name.

        When `qualify_cross_module_links` is enabled, the text of a link to an object defined in a different module
        than the referencing context is prefixed with the target object's module short-name (e.g. `canvas.users`).
        """

        if not self.options.qualify_cross_module_links:
            return None
        if obj.__module__ == context.module.__name__:
            return None
        module_short_name = obj.__module__.split(".")[-1]
        return f"{module_short_name}.{name}"

    def _type_link(self, cls: NewType | type[Any], context: Context) -> str:
        if isinstance(cls, NewType):
            if self._is_in_batch(cls):
                return new_type_link(cls, context, text=self._link_text(cls, type_name(cls), context))
            else:
                return safe_name(type_name(cls))
        else:
            return self._class_link(cls, context)

    def _class_link(self, cls: type[Any], context: Context) -> str:
        "Creates a link to a class if it is part of the exported batch."

        if cls.__module__ == "builtins":
            if issubclass(cls, BaseException):
                return f"[{cls.__name__}](https://docs.python.org/3/library/exceptions.html#{cls.__name__})"

            # built-in type such as `bool`, `int` or `str`
            return cls.__name__
        elif self.options.stdlib_links and (cls.__module__ in sys.builtin_module_names or cls.__module__ in sys.stdlib_module_names):
            # standard library reference
            qualname = f"{cls.__module__}.{cls.__qualname__}"
            return f"[{qualname}](https://docs.python.org/3/library/{cls.__module__}.html#{qualname})"

        if self._is_in_batch(cls):
            return class_link(cls, context, text=self._link_text(cls, cls.__name__, context))
        else:
            return safe_name(cls.__name__)

    def _decorator_link(self, fn: CallableType, context: Context) -> str:
        "Creates a link to a decorator function if it is part of the exported batch."

        if self._is_in_batch(fn):
            return decorator_link(fn, context)
        else:
            return f"@{safe_name(fn.__name__)}"

    def _function_link(self, fn: CallableType, context: Context) -> str:
        "Creates a link to a function if it is part of the exported batch."

        if self._is_in_batch(fn):
            return function_link(fn, context)
        else:
            return safe_name(fn.__name__)

    def _replace_refs(self, text: str, resolver: Resolver, context: Context) -> str:
        "Replaces references in module, class or parameter doc-string text."

        def _replace_module_ref(m: re.Match[str]) -> str:
            ref: str = _extract_ref(m.group(1))
            obj: Any = resolver.evaluate(ref)
            if not isinstance(obj, ModuleType):
                raise ValueError(f"expected: module reference; got: {obj} of type {type(obj)}")
            return self._module_link(obj, context)

        def _replace_class_ref(m: re.Match[str]) -> str:
            ref = _extract_ref(m.group(1))
            obj: Any = resolver.evaluate(ref)
            if isinstance(obj, ModuleType) or is_function(obj) or not isinstance(obj, (NewType, type)):
                raise ValueError(f"expected: class reference; got: {obj} of type {type(obj)}")
            return self._type_link(obj, context)

        def _replace_deco_ref(m: re.Match[str]) -> str:
            ref: str = _extract_ref(m.group(1))
            obj: Any = resolver.evaluate(ref)
            if not is_function(obj):
                raise ValueError(f"expected: decorator reference; got: {obj} of type {type(obj)}")
            return self._decorator_link(obj, context)

        def _replace_func_ref(m: re.Match[str]) -> str:
            ref: str = _extract_ref(m.group(1))
            obj: Any = resolver.evaluate(ref)
            if not is_function(obj):
                raise ValueError(f"expected: function reference; got: {obj} of type {type(obj)}")
            return self._function_link(obj, context)

        regex = re.compile(r":mod:`([^`]+)`")
        text = regex.sub(_replace_module_ref, text)

        regex = re.compile(r":class:`([^`]+)`")
        text = regex.sub(_replace_class_ref, text)

        regex = re.compile(r":exc:`([^`]+)`")
        text = regex.sub(_replace_class_ref, text)

        regex = re.compile(r":deco:`([^`]+)`")
        text = regex.sub(_replace_deco_ref, text)

        regex = re.compile(r":func:`([^`]+)`")
        text = regex.sub(_replace_func_ref, text)

        regex = re.compile(r":meth:`([^`]+)`")
        text = regex.sub(_replace_func_ref, text)

        return text

    def _transform_text(self, text: str, resolver: Resolver, context: Context) -> str:
        """
        Applies transformations to module, class or parameter doc-string text.

        :param text: Text to apply transformations to.
        :param resolver: Resolves references to their corresponding Python types.
        :param context: The module in which the transformation is operating, used to shorten local links.
        """

        text = text.strip()
        text = replace_links(text)
        text = self._replace_refs(text, resolver, context)
        return text

    def _create_context(self, module: ModuleType, partition: ObjectKind) -> Context:
        if self._router is not None:
            return Context(module, None, router=self._router)
        match self.options.partition_strategy:
            case PartitionStrategy.SINGLE:
                return Context(module, None)
            case PartitionStrategy.BY_KIND:
                return Context(module, partition)

    def _generate_enum(self, cls: type[Enum], w: MarkdownWriter) -> None:
        "Writes Markdown output for a single Python enumeration class with all enumeration members."

        module = sys.modules[cls.__module__]
        docstring = parse_type(cls)
        description = docstring.full_description
        if description:
            w.print(self._transform_text(description, ClassResolver(cls), self._create_context(module, ObjectKind.ENUM)))
            w.print()

        w.print("**Members:**")
        w.print()
        try:
            labels = enum_labels(cls)
            for e in cls:
                enum_def = f"* **{safe_name(e.name)}** = {quote_value(e.value)}"
                enum_label = labels.get(e.name)
                if enum_label is not None:
                    w.print(f"{enum_def} - {enum_label}")
                else:
                    w.print(enum_def)
        except OSError:  # source code not available
            # some special constructs (e.g. dynamically generated code) don't have source
            for e in cls:
                enum_def = f"* **{safe_name(e.name)}** = {quote_value(e.value)}"
                w.print(enum_def)

        w.print()

    def _generate_bases(self, cls: type, w: MarkdownWriter) -> None:
        "Writes base classes for a Python class."

        module = sys.modules[cls.__module__]
        bases = [b for b in cls.__bases__ if b is not object]
        context = self._create_context(module, ObjectKind.CLASS)
        if len(bases) > 0:
            w.print(f"**Bases:** {', '.join(self._class_link(b, context) for b in bases)}")
            w.print()

    def _generate_references(self, references: list[DocstringSeeAlso], w: MarkdownWriter) -> None:
        "Writes references defined in a doc-string with `:see:`."

        if references:
            w.print("**References:**")
            w.print()
            for reference in references:
                w.print(f"* {reference.text}")
            w.print()

    def _generate_function(
        self,
        function: CallableType,
        signature_resolver: Resolver,
        param_resolver: Resolver,
        context: Context,
        fmt: MarkdownTypeFormatter,
        w: MarkdownWriter,
    ) -> None:
        "Writes Markdown output for a single Python function."

        docstring = parse_type(function)
        description = docstring.full_description

        signature = inspect.signature(function)
        func_params: list[str] = []
        for param_name, param in signature.parameters.items():
            if param.annotation is not inspect.Signature.empty:
                param_type = fmt.type_to_markdown(param.annotation)
                func_params.append(f"{param_name}: {param_type}")
            else:
                func_params.append(param_name)
        param_list = ", ".join(func_params)
        if signature.return_annotation is not inspect.Signature.empty:
            function_returns = fmt.type_to_markdown(signature.return_annotation)
            returns = f" → {function_returns}"
        else:
            returns = ""
        title = f"{safe_name(function.__name__)} ( {param_list} ){returns}"
        w.print(f"### {self._heading_anchor(function_anchor(function), title)}")
        w.print()

        if description:
            w.print(self._transform_text(description, signature_resolver, context))
            w.print()

        if docstring.params:
            w.print("**Parameters:**")
            w.print()

            for param_name, docstring_param in docstring.params.items():
                param_item = f"**{safe_name(param_name)}**"
                param_desc = self._transform_text(docstring_param.description, param_resolver, context)
                if docstring_param.param_type is not inspect.Signature.empty:
                    param_type = fmt.type_to_markdown(docstring_param.param_type)
                    w.print(f"* {param_item} ({param_type}) - {param_desc}")
                else:
                    w.print(f"* {param_item} - {param_desc}")
            w.print()

        if docstring.returns:
            returns_desc = self._transform_text(docstring.returns.description, param_resolver, context)
            if docstring.returns.return_type is not inspect.Signature.empty:
                return_type = fmt.type_to_markdown(docstring.returns.return_type)
                w.print(f"**Returns:** ({return_type}) - {returns_desc}")
            else:
                w.print(f"**Returns:** {returns_desc}")
            w.print()

        self._generate_references(docstring.see_also, w)

    def _generate_functions(self, cls: type, fmt: MarkdownTypeFormatter, w: MarkdownWriter) -> None:
        "Writes Markdown output for Python member functions in a class."

        for name, func in inspect.getmembers(cls, lambda f: is_function(f)):
            # skip inherited functions (unless overridden)
            if name not in cls.__dict__:
                continue

            # skip private functions
            if not self.options.include_private and is_private(func):
                continue

            # skip functions without documentation
            if not self.options.include_undocumented and not is_documented(func):
                continue

            module = sys.modules[func.__module__]
            context = self._create_context(module, ObjectKind.CLASS)
            self._generate_function(func, ClassResolver(cls), MemberFunctionResolver(cls, func), context, fmt, w)  # pyright: ignore[reportArgumentType]

    def _generate_class(self, cls: type, w: MarkdownWriter) -> None:
        "Writes Markdown output for a single (regular) Python class."

        self._generate_bases(cls, w)

        module = sys.modules[cls.__module__]
        context = self._create_context(module, ObjectKind.CLASS)

        fmt = MarkdownTypeFormatter(module, lambda c: self._type_link(c, context), self.options.auxiliary_types)

        docstring = parse_type(cls)
        description = docstring.full_description
        if description:
            w.print(self._transform_text(description, ClassResolver(cls), context))
            w.print()

        self._generate_references(docstring.see_also, w)

        self._generate_functions(cls, fmt, w)

    def _generate_dataclass(self, cls: type, w: MarkdownWriter) -> None:
        "Writes Markdown output for a single Python data-class."

        self._generate_bases(cls, w)

        module = sys.modules[cls.__module__]
        context = self._create_context(module, ObjectKind.DATACLASS)

        fmt = MarkdownTypeFormatter(module, lambda c: self._type_link(c, context), self.options.auxiliary_types)

        docstring = parse_type(cls)
        if docstring.short_description or docstring.params:
            check_docstring(cls, docstring, strict=True)
        description = docstring.full_description
        if description:
            w.print(self._transform_text(description, ClassResolver(cls), context))
            w.print()

        if docstring.params:
            w.print("**Properties:**")
            w.print()

            for name, docstring_param in docstring.params.items():
                param_type = fmt.type_to_markdown(docstring_param.param_type)
                param_desc = self._transform_text(docstring_param.description, MemberResolver(cls, name), context)
                w.print(f"* **{safe_name(name)}** ({param_type}) - {param_desc}")
            w.print()

        self._generate_references(docstring.see_also, w)

        self._generate_functions(cls, fmt, w)

    def _generate_module_functions(self, module: ModuleType, functions: list[FunctionType], w: MarkdownWriter) -> None:
        "Writes Markdown output for a group of module-level functions defined in a single module."

        context = self._create_context(module, ObjectKind.FUNCTION)
        fmt = MarkdownTypeFormatter(module, lambda c: self._type_link(c, context), self.options.auxiliary_types)
        for func in functions:
            self._generate_function(func, ModuleResolver(module), ModuleFunctionResolver(func), context, fmt, w)

    def _generate_module(self, module: ModuleType, target: Path, partition: ObjectKind | None) -> None:
        "Writes Markdown output for a single Python module."

        context = self._create_context(module, ObjectKind.MODULE)
        fmt = MarkdownTypeFormatter(module, lambda c: self._type_link(c, context), self.options.auxiliary_types)

        header = MarkdownWriter()
        module_name = module.__name__.split(".")[-1]
        header.print(f"# {self._heading_anchor(module_anchor(module), module_name)}")
        header.print()

        docstring = parse_type(module)
        if docstring.full_description:
            header.print(self._transform_text(docstring.full_description, ModuleResolver(module), context))
            header.print()

        self._generate_references(docstring.see_also, header)

        w = MarkdownWriter()
        for nt in get_module_new_types(module):
            w.print(f"## {self._heading_anchor(new_type_anchor(nt), safe_name(type_name(nt)))}")
            w.print()
            w.print(f"**Supertype:** {self._type_link(nt.__supertype__, context)}")

        for cls in get_module_classes(module):
            if not self.options.include_private and is_private(cls):
                continue

            if self.predicate is not None and not self.predicate(cls):
                continue

            # check whether the current object is to be exported
            if partition is not None:
                if is_type_enum(cls):
                    if partition is not ObjectKind.ENUM:
                        continue
                elif is_dataclass(cls):
                    if partition is not ObjectKind.DATACLASS:
                        continue
                elif isinstance(cls, type):
                    if partition is not ObjectKind.CLASS:
                        continue

            # required to suppress type checker warnings
            kls = typing.cast(type, cls)  # type: ignore[redundant-cast]

            w.print(f"## {self._heading_anchor(class_anchor(kls), safe_name(kls.__name__))}")
            w.print()

            try:
                if is_type_enum(kls):
                    self._generate_enum(kls, w)
                elif is_dataclass(kls):
                    self._generate_dataclass(kls, w)
                elif isinstance(kls, type):
                    self._generate_class(kls, w)
                else:
                    raise TypeError(f"expected: data-class, enum class or regular class; got: {kls}")
            except Exception as e:
                kls = typing.cast(type, cls)  # type: ignore[redundant-cast]
                raise ProcessingError(
                    f"error while processing type `{kls.__name__}` in module `{module.__name__}`",
                    obj=kls,
                ) from e

        if partition is None or partition is ObjectKind.FUNCTION:
            # generate top-level module functions
            functions = get_module_functions(module)
            if not self.options.include_private:
                functions = [fn for fn in functions if not is_private(fn)]
            if not self.options.include_undocumented:
                functions = [fn for fn in functions if is_documented(fn)]
            if functions:
                anchor = f"{safe_id(module.__name__)}-functions"
                anchored_title = self._heading_anchor(anchor, "Functions")
                w.print(f"## {anchored_title}")
                w.print()

                for func in functions:
                    self._generate_function(func, ModuleResolver(module), ModuleFunctionResolver(func), context, fmt, w)

        if w:
            with open(target, "w", encoding="utf-8") as f:
                f.write(header.fetch())
                f.write("\n")
                f.write(w.fetch())

    def _collect_buckets(self) -> dict[RouteKey, Bucket]:
        """
        First routing pass: assigns every documented object to an output-file bucket.

        Walks all modules, applies the same visibility filters as module-based generation, then calls the routing
        callable. Objects routed to `None` are excluded. Returns buckets keyed by routing key, in discovery order.
        """

        assert self.route is not None
        buckets: dict[RouteKey, Bucket] = {}
        seen: set[int] = set()

        def bucket_for(key: RouteKey) -> Bucket:
            bucket = buckets.get(key)
            if bucket is None:
                bucket = Bucket(key)
                buckets[key] = bucket
            return bucket

        for module in self.modules:
            for nt in get_module_new_types(module):
                routed = self.route(nt)
                if routed is None or id(nt) in seen:
                    continue
                seen.add(id(nt))
                file_key, section_key = _split_routed_key(routed)
                bucket_for(file_key).section_for(section_key).new_types.append(nt)

            for cls in get_module_classes(module):
                if not self.options.include_private and is_private(cls):
                    continue
                if self.predicate is not None and not self.predicate(cls):
                    continue
                routed = self.route(cls)
                if routed is None or id(cls) in seen:
                    continue
                seen.add(id(cls))
                file_key, section_key = _split_routed_key(routed)
                bucket_for(file_key).section_for(section_key).classes.append(typing.cast(type, cls))  # type: ignore[redundant-cast]

            functions = get_module_functions(module)
            if not self.options.include_private:
                functions = [fn for fn in functions if not is_private(fn)]
            if not self.options.include_undocumented:
                functions = [fn for fn in functions if is_documented(fn)]
            for func in functions:
                routed = self.route(func)
                if routed is None or id(func) in seen:
                    continue
                seen.add(id(func))
                file_key, section_key = _split_routed_key(routed)
                bucket_for(file_key).section_for(section_key).functions.append(func)

        return buckets

    def _build_router(self, buckets: dict[RouteKey, Bucket]) -> Router:
        "Builds the routing lookup tables (object identity → key, module name → a key it contributes to)."

        object_keys: dict[tuple[str, str], RouteKey] = {}
        module_keys: dict[str, RouteKey] = {}
        for key, bucket in buckets.items():
            seen_anchors: set[str] = set()

            def register(obj: NewType | ObjectType, anchor: str, *, key: RouteKey = key, seen: set[str] = seen_anchors) -> None:
                object_keys[_object_route_id(obj)] = key
                module_keys.setdefault(obj.__module__, key)
                if anchor in seen:
                    logging.warning("duplicate anchor %r in output file %r; links to it may be ambiguous", anchor, key)
                seen.add(anchor)

            # links resolve to the output FILE, not the section, so register every object to the file key
            for section in bucket.sections.values():
                for nt in section.new_types:
                    register(nt, new_type_anchor(nt))
                for kls in section.classes:
                    register(kls, class_anchor(kls))
                for func in section.functions:
                    register(func, function_anchor(func))
        return Router(buckets, self._file_meta, object_keys, module_keys)

    def _generate_bucket(self, bucket: Bucket, target: Path) -> None:
        "Second routing pass: writes a single routed output file from a bucket of objects."

        assert self._router is not None
        meta = self._file_meta(bucket.key)

        header = MarkdownWriter()
        if meta is not None and meta.front_matter:
            header.print("---")
            for fm_key, fm_value in meta.front_matter.items():
                header.print(f"{_yaml_scalar(fm_key)}: {_yaml_scalar(fm_value)}")
            header.print("---")
            header.print()

        title = meta.title if meta is not None and meta.title is not None else bucket.key
        header.print(f"# {self._heading_anchor(safe_id(bucket.key), title)}")
        header.print()

        w = MarkdownWriter()
        for section in self._ordered_sections(bucket, meta):
            self._emit_section_objects(section, w)

        if w:
            os.makedirs(target.parent, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(header.fetch())
                f.write("\n")
                f.write(w.fetch())

    def _ordered_sections(self, bucket: Bucket, meta: FileMeta | None) -> list[Section]:
        "Returns the bucket's sections in emission order: declared `section_order` first, then any remaining ones."

        if meta is None or meta.section_order is None:
            return list(bucket.sections.values())

        ordered: list[Section] = []
        emitted: set[SectionKey | None] = set()
        for declared_key in meta.section_order:
            section = bucket.sections.get(declared_key)
            if section is not None:
                ordered.append(section)
                emitted.add(declared_key)
        for section_key, section in bucket.sections.items():
            if section_key not in emitted:
                if section_key is not None:
                    logging.warning("section %r in file %r is not listed in section_order; emitting it last", section_key, bucket.key)
                ordered.append(section)
        return ordered

    def _emit_section_objects(self, section: Section, w: MarkdownWriter) -> None:
        "Writes a section's new types, classes and module-level functions, in that order."

        for nt in section.new_types:
            module = sys.modules[nt.__module__]
            context = self._create_context(module, ObjectKind.MODULE)
            w.print(f"## {self._heading_anchor(new_type_anchor(nt), safe_name(type_name(nt)))}")
            w.print()
            w.print(f"**Supertype:** {self._type_link(nt.__supertype__, context)}")

        for kls in section.classes:
            w.print(f"## {self._heading_anchor(class_anchor(kls), safe_name(kls.__name__))}")
            w.print()
            try:
                if is_type_enum(kls):
                    self._generate_enum(kls, w)
                elif is_dataclass(kls):
                    self._generate_dataclass(kls, w)
                elif isinstance(kls, type):
                    self._generate_class(kls, w)
                else:
                    raise TypeError(f"expected: data-class, enum class or regular class; got: {kls}")
            except Exception as e:
                raise ProcessingError(
                    f"error while processing type `{kls.__name__}` in module `{kls.__module__}`",
                    obj=kls,
                ) from e

        # group functions by their defining module so the context and type formatter are created once per module
        functions_by_module: dict[str, list[FunctionType]] = {}
        for func in section.functions:
            functions_by_module.setdefault(func.__module__, []).append(func)
        for module_name, module_functions in functions_by_module.items():
            module = sys.modules[module_name]
            self._generate_module_functions(module, module_functions, w)

    def _generate_routed(self, target: Path) -> None:
        "Generates Markdown output grouped into files by the routing callable."

        buckets = self._collect_buckets()
        self._router = self._build_router(buckets)
        try:
            filenames: dict[str, RouteKey] = {}
            for key, bucket in buckets.items():
                self._router.current_key = key
                filename = self._router.filename_of_key(key)
                if Path(filename).is_absolute() or ".." in Path(filename).parts:
                    raise ValueError(f"invalid output file name for routing key {key!r}: {filename!r}")
                if filename in filenames and filenames[filename] != key:
                    raise ValueError(f"routing keys {filenames[filename]!r} and {key!r} map to the same file {filename!r}")
                filenames[filename] = key
                self._generate_bucket(bucket, target / Path(filename))
        finally:
            self._router = None

    def generate(self, target: Path) -> None:
        """
        Writes Markdown files to a target directory.

        Without routing, one file is written per module (or per module and kind under `BY_KIND`), and the
        subdirectories that files are written to match the hierarchy of the Python modules. With a routing callable
        set, objects are grouped into files by routing key instead.
        """

        if self._routing_enabled:
            self._generate_routed(target)
            return

        for module in self.modules:
            module_path = module.__name__.replace(".", "/") + ".md"
            path = target / Path(module_path)
            os.makedirs(path.parent, exist_ok=True)

            match self.options.partition_strategy:
                case PartitionStrategy.SINGLE:
                    self._generate_module(module, path, None)
                case PartitionStrategy.BY_KIND:
                    for partition in [ObjectKind.DATACLASS, ObjectKind.ENUM, ObjectKind.CLASS, ObjectKind.FUNCTION]:
                        partition_path = path.with_stem(f"{path.stem}-{partition.value}")
                        self._generate_module(module, partition_path, partition)


def generate_markdown(modules: list[ModuleType], out_dir: Path, *, options: MarkdownOptions | None = None) -> None:
    """
    Generates Markdown documentation for a list of modules.

    :param modules: The list of modules to generate documentation for.
    :param out_dir: Directory to write Markdown files to.
    :param options: Options for generating Markdown output.
    """

    if not modules:
        raise ValueError("no Python module given")
    if options is None:
        options = MarkdownOptions()

    MarkdownGenerator(modules, options=options).generate(out_dir)
