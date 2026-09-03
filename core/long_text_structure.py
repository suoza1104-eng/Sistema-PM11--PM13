"""Structured long-text utilities for PM13.

The application keeps the SAP-facing ``text`` column as the canonical rendered
plain text, while optional JSON metadata enables Word-like hierarchical editing.
This module is intentionally dependency-free so the same parser can be used by
imports, API saves, standards and exports.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

MODE_FREE = "FREE"
MODE_STRUCTURED = "STRUCTURED"
MODE_MIXED = "MIXED"

# Tolerates: 1.1 text | 1.1. text | 1.1-text | 1.1_text | 1.1) text | tabs/spaces.
# The numeric path is anchored at the start of the line to avoid interpreting
# measurements that occur inside a sentence (e.g. CABO 2.5 MM2).
_MARKER_RE = re.compile(
    r"^\s*(?P<num>\d+(?:\s*\.\s*\d+){0,7})\s*"
    r"(?P<sep>(?:[.)]|[-–—_:]))?\s*(?P<body>.*)$",
    re.UNICODE,
)

_MEASUREMENT_TOKEN_RE = re.compile(
    r"^(?:MM(?:2|²)?|CM|M|KM|KW|W|V|KV|A|MA|BAR|PSI|HZ|RPM|OHM|Ω|CV|HP|KG|G|L|ML)\b",
    re.IGNORECASE,
)


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _normalize_eol(text: Any) -> str:
    value = "" if text is None else str(text)
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _candidate(line: str) -> Optional[Dict[str, Any]]:
    if not line.strip():
        return None
    match = _MARKER_RE.match(line)
    if not match:
        return None
    raw_num = re.sub(r"\s+", "", match.group("num") or "")
    try:
        path = [int(part) for part in raw_num.split(".")]
    except (TypeError, ValueError):
        return None
    if not path or any(part < 0 for part in path):
        return None
    body = (match.group("body") or "").strip()
    sep = match.group("sep") or ""
    # A line such as "1.1 KW" can be a measurement, not a topic. Keep the
    # candidate but mark it as suspicious so document-level confidence can reject it.
    suspicious_measurement = bool(len(path) > 1 and not sep and _MEASUREMENT_TOKEN_RE.match(body))
    return {
        "path": path,
        "level": len(path),
        "body": body,
        "separator": sep,
        "suspicious_measurement": suspicious_measurement,
    }


def _transition_score(previous: List[int], current: List[int]) -> int:
    """Return confidence points for a plausible outline transition."""
    if not previous or not current:
        return 0
    # Same parent, next sibling: 1.1 -> 1.2 / 2 -> 3
    if len(previous) == len(current) and previous[:-1] == current[:-1] and current[-1] == previous[-1] + 1:
        return 3
    # Descend exactly one level: 1 -> 1.1 or 1.2 -> 1.2.1
    if len(current) == len(previous) + 1 and current[:-1] == previous:
        return 4
    # Return to an ancestor's next sibling: 1.2.3 -> 1.3 / 1.2.3 -> 2
    if len(current) < len(previous):
        prefix = previous[: len(current) - 1]
        if current[:-1] == prefix and current[-1] == previous[len(current) - 1] + 1:
            return 3
    # Missing parent but coherent siblings: 1.1 -> 1.2
    if len(previous) == len(current) and previous[:-1] == current[:-1] and current[-1] > previous[-1]:
        return 2
    return 0


def detect_structure(text: Any) -> Dict[str, Any]:
    """Parse a text into hierarchical/free nodes without inventing topics.

    Returns: ``mode``, ``nodes``, ``rendered_text``, ``confidence`` and diagnostics.
    If confidence is insufficient, mode is FREE and the text remains untouched.
    """
    original = _normalize_eol(text)
    lines = original.split("\n")
    candidates: List[Tuple[int, Dict[str, Any]]] = []
    for idx, line in enumerate(lines):
        cand = _candidate(line)
        if cand:
            candidates.append((idx, cand))

    if not candidates:
        return {
            "mode": MODE_FREE,
            "nodes": [],
            "structure_json": None,
            "rendered_text": original,
            "confidence": 0.0,
            "topic_count": 0,
            "free_line_count": len([ln for ln in lines if ln.strip()]),
        }

    score = 0
    strong_separators = 0
    suspicious = 0
    previous = None
    for _, cand in candidates:
        if cand["separator"]:
            strong_separators += 1
        if cand["suspicious_measurement"]:
            suspicious += 1
        if previous is not None:
            score += _transition_score(previous, cand["path"])
        previous = cand["path"]

    # Presence of a parent/child pair anywhere is strong evidence.
    paths = [cand["path"] for _, cand in candidates]
    parent_child_pairs = 0
    path_tuples = {tuple(path) for path in paths}
    for path in paths:
        if len(path) > 1 and tuple(path[:-1]) in path_tuples:
            parent_child_pairs += 1
            score += 3

    nonempty_lines = [ln for ln in lines if ln.strip()]
    candidate_ratio = len(candidates) / max(1, len(nonempty_lines))
    score += min(3, strong_separators)
    score += 2 if candidate_ratio >= 0.5 else 0
    score -= suspicious * 3

    # Minimum evidence: two coherent markers, a parent/child pair, or explicit subtopics.
    coherent = (len(candidates) >= 2 and (score >= 3 or parent_child_pairs > 0)) or any(len(c["path"]) > 1 and not c.get("suspicious_measurement") for _, c in candidates)
    if not coherent:
        return {
            "mode": MODE_FREE,
            "nodes": [],
            "structure_json": None,
            "rendered_text": original,
            "confidence": max(0.0, min(0.49, score / 10.0)),
            "topic_count": 0,
            "free_line_count": len(nonempty_lines),
        }

    candidate_by_line = {idx: cand for idx, cand in candidates}
    nodes: List[Dict[str, Any]] = []
    previous_content_line = ""
    had_free_line_since_last_topic = False
    last_topic_first_num = None

    for idx, line in enumerate(lines):
        cand = candidate_by_line.get(idx)
        if cand:
            first_num = cand["path"][0] if cand["path"] else 1
            should_restart = False
            if last_topic_first_num is not None:
                if first_num == 1 and (had_free_line_since_last_topic or last_topic_first_num > 1):
                    should_restart = True
                elif first_num < last_topic_first_num:
                    should_restart = True

            node = {
                "id": _uid(),
                "type": "topic",
                "level": max(1, min(8, int(cand["level"]))),
                "text": cand["body"],
                "path": cand["path"],
            }
            if should_restart:
                node["restart_numbering"] = True

            nodes.append(node)
            previous_content_line = cand["body"]
            last_topic_first_num = first_num
            had_free_line_since_last_topic = False
        elif not line.strip():
            nodes.append({
                "id": _uid(),
                "type": "free",
                "level": 0,
                "text": line,
            })
            previous_content_line = ""
        elif (
            nodes
            and nodes[-1]["type"] == "topic"
            and previous_content_line
            and not re.search(r"[.!?;:]\s*$", previous_content_line)
            and not re.search(r":\s*$", line)
            and not re.match(r"^\s*(?:#{1,6}\s|[-*]\s+|\([ xX]\))", line)
        ):
            nodes[-1]["text"] = f'{nodes[-1]["text"].rstrip()} {line.strip()}'
            previous_content_line = line.strip()
        else:
            nodes.append({
                "id": _uid(),
                "type": "free",
                "level": 0,
                "text": line,
            })
            previous_content_line = line.strip()
            if line.strip():
                had_free_line_since_last_topic = True

    has_free_content = any(n["type"] == "free" and str(n.get("text") or "").strip() for n in nodes)
    mode = MODE_MIXED if has_free_content else MODE_STRUCTURED
    rendered = render_nodes(nodes)
    confidence = min(1.0, 0.55 + score / max(12.0, len(candidates) * 4.0))
    return {
        "mode": mode,
        "nodes": nodes,
        "structure_json": json.dumps(nodes, ensure_ascii=False),
        "rendered_text": rendered,
        "confidence": confidence,
        "topic_count": len(candidates),
        "free_line_count": sum(1 for n in nodes if n["type"] == "free" and str(n.get("text") or "").strip()),
    }


def normalize_nodes(nodes: Any) -> List[Dict[str, Any]]:
    if isinstance(nodes, str):
        try:
            nodes = json.loads(nodes)
        except (TypeError, ValueError, json.JSONDecodeError):
            nodes = []
    if not isinstance(nodes, list):
        return []
    normalized: List[Dict[str, Any]] = []
    previous_topic_level = 0
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        node_type = "free" if str(raw.get("type") or "topic").lower() == "free" else "topic"
        text = _normalize_eol(raw.get("text") or "").replace("\n", " ").strip() if node_type == "topic" else _normalize_eol(raw.get("text") or "")
        if node_type == "free":
            level = 0
        else:
            try:
                level = int(raw.get("level") or 1)
            except (TypeError, ValueError):
                level = 1
            level = max(1, min(8, level))
            if previous_topic_level and level > previous_topic_level + 1:
                level = previous_topic_level + 1
            previous_topic_level = level
        
        n_dict = {
            "id": str(raw.get("id") or _uid()),
            "type": node_type,
            "level": level,
            "text": text,
        }
        if node_type == "topic":
            if isinstance(raw.get("path"), list):
                n_dict["path"] = [int(x) for x in raw.get("path") if str(x).isdigit()]
            if raw.get("restart_numbering"):
                n_dict["restart_numbering"] = True
            if raw.get("resume_numbering"):
                n_dict["resume_numbering"] = True

        normalized.append(n_dict)
    return normalized


def number_nodes(nodes: Any) -> List[Dict[str, Any]]:
    counters: List[int] = []
    suspended_counters: List[List[int]] = []
    numbered: List[Dict[str, Any]] = []
    all_nodes = normalize_nodes(nodes)
    for node in all_nodes:
        item = dict(node)
        if item["type"] != "topic":
            item["number"] = ""
            numbered.append(item)
            continue
        level = node["level"]
        path = node.get("path")
        if node.get("restart_numbering"):
            if counters:
                suspended_counters.append(list(counters))
            counters = list(path) if isinstance(path, list) and len(path) == level else [1] * level
        elif node.get("resume_numbering") and suspended_counters:
            counters = suspended_counters.pop()
            level = len(counters)
            counters[-1] += 1
        elif not counters:
            if len(all_nodes) == 1 and isinstance(path, list) and len(path) == level:
                counters = list(path)
            else:
                counters = [1] * level
        elif level > len(counters):
            counters.extend([1] * (level - len(counters)))
        elif level == len(counters):
            counters[-1] += 1
        else:
            counters = counters[:level]
            counters[-1] += 1
        item["number"] = ".".join(str(v) for v in counters)
        numbered.append(item)
    return numbered


def render_nodes(nodes: Any) -> str:
    rendered: List[str] = []
    for node in number_nodes(nodes):
        text = str(node.get("text") or "")
        if node["type"] == "topic":
            number = node.get("number") or ""
            rendered.append(f"{number} {text}".rstrip())
        else:
            rendered.append(text)
    return "\n".join(rendered)


def _restore_blank_line_layout(nodes: Any, text: Any) -> List[Dict[str, Any]]:
    """Merge blank lines from canonical text into otherwise equivalent nodes.

    Older structured records discarded empty lines from ``structure_json`` while
    retaining them in ``text``.  The SAP preview materializes JSON, so those
    records appeared compacted.  Only reconcile when every nonblank rendered
    line is identical; content or numbering differences are never overwritten.
    """
    normalized = normalize_nodes(nodes)
    raw_lines = _normalize_eol(text).split("\n")
    numbered = number_nodes(normalized)

    def rendered_line(node: Dict[str, Any]) -> str:
        value = str(node.get("text") or "")
        if node["type"] == "topic":
            return f'{node.get("number") or ""} {value}'.rstrip()
        return value

    node_lines = [rendered_line(node) for node in numbered]
    if [line for line in raw_lines if line.strip()] != [line for line in node_lines if line.strip()]:
        return normalized

    content_nodes = [
        node for node, numbered_node in zip(normalized, numbered)
        if rendered_line(numbered_node).strip()
    ]
    restored: List[Dict[str, Any]] = []
    content_index = 0
    for line in raw_lines:
        if line.strip():
            restored.append(content_nodes[content_index])
            content_index += 1
        else:
            restored.append({"id": _uid(), "type": "free", "level": 0, "text": line})
    return restored


def prepare_for_save(text: Any = "", structure_mode: Optional[str] = None,
                     structure_json: Any = None, source_text_original: Any = None) -> Dict[str, Any]:
    """Canonicalize a save payload.

    If explicit structured JSON is present it wins and ``text`` is regenerated.
    Otherwise the parser detects existing numbering. Free text is never numbered.
    """
    requested_mode = str(structure_mode or "").upper().strip()
    raw = _normalize_eol(text)
    nodes = normalize_nodes(structure_json)
    if nodes and requested_mode in {MODE_STRUCTURED, MODE_MIXED}:
        nodes = _restore_blank_line_layout(nodes, raw)
        has_topic = any(n["type"] == "topic" for n in nodes)
        has_free = any(n["type"] == "free" and str(n.get("text") or "").strip() for n in nodes)
        mode = MODE_MIXED if has_topic and has_free else MODE_STRUCTURED if has_topic else MODE_FREE
        if mode != MODE_FREE:
            rendered = render_nodes(nodes)
            return {
                "text": rendered if rendered.strip() else raw,
                "structure_mode": mode,
                "structure_json": json.dumps(nodes, ensure_ascii=False),
                "source_text_original": raw,
            }

    raw = _normalize_eol(text)
    if requested_mode == MODE_FREE:
        return {
            "text": raw,
            "structure_mode": MODE_FREE,
            "structure_json": None,
            "source_text_original": raw,
        }

    parsed = detect_structure(raw)
    return {
        "text": parsed["rendered_text"],
        "structure_mode": parsed["mode"],
        "structure_json": parsed["structure_json"],
        "source_text_original": raw,
    }


def materialize_record(record: Dict[str, Any]) -> str:
    """Return the exact SAP/export text, preserving canonical saved text when consistent."""
    if not record:
        return ""
    mode = str(record.get("structure_mode") or "").upper()
    if mode in {MODE_STRUCTURED, MODE_MIXED} and record.get("structure_json"):
        nodes = normalize_nodes(record.get("structure_json"))
        if nodes:
            text_val = _normalize_eol(record.get("text") or "")
            rendered = render_nodes(_restore_blank_line_layout(nodes, text_val))
            
            def _strip_marker(s: str) -> str:
                return _MARKER_RE.sub(r"\g<body>", str(s or "")).strip()

            raw_node_texts = [_strip_marker(n.get("text")) for n in nodes if _strip_marker(n.get("text"))]
            raw_val_lines = [_strip_marker(line) for line in text_val.split("\n") if _strip_marker(line)]
            if text_val.strip() and raw_val_lines == raw_node_texts:
                return text_val
            return rendered
    text_val = _normalize_eol(record.get("text") or "")
    if text_val.strip():
        return text_val
    return _normalize_eol(record.get("source_text_original") or "")


def extract_block(nodes: Any, index: int) -> List[Dict[str, Any]]:
    """Return selected topic + descendants, normalized so its root is level 1."""
    data = normalize_nodes(nodes)
    if index < 0 or index >= len(data) or data[index]["type"] != "topic":
        return []
    root_level = data[index]["level"]
    end = index + 1
    while end < len(data):
        node = data[end]
        if node["type"] == "topic" and node["level"] <= root_level:
            break
        end += 1
    block = []
    for node in data[index:end]:
        copy = dict(node)
        copy["id"] = _uid()
        if copy["type"] == "topic":
            copy["level"] = max(1, copy["level"] - root_level + 1)
        block.append(copy)
    return block
