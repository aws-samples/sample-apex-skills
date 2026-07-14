#!/usr/bin/env python3
"""Load SKILL.md YAML frontmatter safely.

This module centralizes how untrusted frontmatter is parsed so every caller
gets the same conservative behavior:

  * frontmatter is bounded in size before it is parsed,
  * YAML anchors and aliases are rejected (they let a small document expand
    into a very large object graph),
  * duplicate keys are rejected (stricter YAML consumers reject them too),
  * only an expected set of top-level keys is allowed, and
  * deeply nested structures are rejected.

Callers use the single public entry point ``load_frontmatter``. Any problem
raises ``FrontmatterError`` with a short, generic message; the offending input
is never echoed back.
"""

import collections.abc

import yaml

# Maximum size, in bytes, of a frontmatter block we are willing to parse.
MAX_FRONTMATTER_BYTES = 64 * 1024

# Maximum number of parse events before we treat the document as pathological.
MAX_EVENTS = 10_000

# The only top-level keys we expect in SKILL.md frontmatter.
ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {"name", "description", "license", "metadata", "allowed-tools"}
)

# Maximum allowed nesting depth of the loaded structure.
MAX_NESTING_DEPTH = 8


class FrontmatterError(Exception):
    """Raised when frontmatter fails a safety or structural check.

    The message is intentionally generic and never includes the raw input.
    """


def _check_size(raw):
    """Reject frontmatter larger than the byte cap."""
    if len(raw.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        raise FrontmatterError(
            f"frontmatter exceeds maximum size of {MAX_FRONTMATTER_BYTES} bytes"
        )


def _check_no_anchors(raw):
    """Reject anchors/aliases, cap parse events, and gate nesting depth.

    Anchors (``&name``) and aliases (``*name``) allow a small document to
    reference and expand shared structure, which can blow up memory. We walk
    the event stream and reject any event that declares an anchor, and bound
    the total event count as a cheap guard against structural explosion.

    The event stream is also the early gate for nesting depth: we track the
    current collection depth (incrementing on each mapping/sequence start and
    decrementing on each end) and reject the document before ``compose`` or
    ``safe_load`` ever recurse. This is what keeps a deeply-nested flow
    document (e.g. hundreds of nested ``[``) from crashing the recursive
    composer/loader with a ``RecursionError``. ``yaml.parse`` itself does not
    recurse in Python, so it is safe to iterate here first.
    """
    try:
        events = 0
        depth = 0
        for event in yaml.parse(raw, Loader=yaml.SafeLoader):
            events += 1
            if events > MAX_EVENTS:
                raise FrontmatterError("frontmatter has too many parse events")
            if getattr(event, "anchor", None) is not None:
                raise FrontmatterError("frontmatter uses YAML anchors or aliases")
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
                if depth > MAX_NESTING_DEPTH:
                    raise FrontmatterError(
                        "frontmatter nesting exceeds maximum depth"
                    )
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
    except yaml.YAMLError as e:
        raise FrontmatterError(f"frontmatter is not valid YAML: {e}") from e


def _check_no_duplicate_keys(raw):
    """Reject any mapping that declares the same key twice.

    ``yaml.safe_load`` silently keeps the last value for a duplicated key, but
    stricter consumers reject the document, so we do too. We inspect the
    composed node tree rather than the loaded object because duplicates are
    already collapsed by the time loading finishes.
    """
    try:
        node = yaml.compose(raw, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError) as e:
        raise FrontmatterError("frontmatter is not valid YAML") from e
    if node is None:
        return
    loader = yaml.SafeLoader("")
    try:
        _walk_for_duplicates(node, loader)
    finally:
        loader.dispose()


def _walk_for_duplicates(node, loader):
    """Recursively check every MappingNode for duplicate keys.

    Constructing a key can fail if the document uses a complex/unhashable key
    (e.g. ``? [a, b]``) or a merge key (``<<:``). Both are rejected with a
    generic ``FrontmatterError`` so that no raw input is echoed back and so
    the caller never sees an uncaught ``yaml`` exception.
    """
    if isinstance(node, yaml.MappingNode):
        seen = set()
        for key_node, value_node in node.value:
            try:
                key = loader.construct_object(key_node, deep=True)
            except (yaml.YAMLError, RecursionError) as e:
                raise FrontmatterError("frontmatter is not valid YAML") from e
            if not isinstance(key, collections.abc.Hashable):
                raise FrontmatterError("frontmatter has an unsupported complex key")
            if key in seen:
                raise FrontmatterError("frontmatter declares a duplicate key")
            seen.add(key)
            _walk_for_duplicates(value_node, loader)
    elif isinstance(node, yaml.SequenceNode):
        for child in node.value:
            _walk_for_duplicates(child, loader)


def _depth(obj):
    """Return the maximum nesting depth of a loaded object."""
    if isinstance(obj, dict):
        if not obj:
            return 1
        return 1 + max(_depth(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        if not obj:
            return 1
        return 1 + max(_depth(v) for v in obj)
    return 0


def load_frontmatter(raw, *, source="<frontmatter>"):
    """Parse a frontmatter string and return it as a dict.

    Runs a fixed sequence of safety and structural checks and raises
    ``FrontmatterError`` on the first violation. ``source`` is accepted for
    caller-side context but is not embedded in error messages.
    """
    _check_size(raw)
    _check_no_anchors(raw)
    _check_no_duplicate_keys(raw)

    try:
        data = yaml.safe_load(raw)
    except (yaml.YAMLError, RecursionError) as e:
        raise FrontmatterError("frontmatter is not valid YAML") from e

    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter is not a mapping")

    unexpected = set(data) - ALLOWED_TOP_LEVEL_KEYS
    if unexpected:
        raise FrontmatterError(
            "frontmatter has unexpected top-level key(s); allowed keys are "
            f"{sorted(ALLOWED_TOP_LEVEL_KEYS)}"
        )

    if _depth(data) > MAX_NESTING_DEPTH:
        raise FrontmatterError(
            f"frontmatter nesting exceeds maximum depth of {MAX_NESTING_DEPTH}"
        )

    return data
