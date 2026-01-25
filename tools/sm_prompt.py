#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, List, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
PROGRESS_PATH = DOCS_DIR / "11-progress.md"

# User requested header filename is "10-chat-started.md"
HEADER_CANDIDATES = [
    DOCS_DIR / "10-chat-started.md",
    DOCS_DIR / "10-chat-starter.md",  # fallback
]

PROMPTS_DIR = DOCS_DIR / "prompts"


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def find_existing_file(base_path: pathlib.Path, exts: Tuple[str, ...] = ("", ".md", ".txt")) -> pathlib.Path:
    """
    Try base_path as-is, then base_path + ext for ext in exts.
    """
    for ext in exts:
        candidate = base_path if ext == "" else base_path.with_suffix(ext)
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find file: {base_path} (tried {exts})")


def get_header_path() -> pathlib.Path:
    for p in HEADER_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Header file not found. Tried: {', '.join(str(p) for p in HEADER_CANDIDATES)}"
    )


def normalize_md_newlines(s: str) -> str:
    # Ensure the concatenation results in clean spacing.
    return s.strip() + "\n"


def ensure_section(md_lines: List[str], heading: str) -> List[str]:
    """
    Ensure a '## <heading>' section exists. If not, create at end.
    """
    header_line = f"## {heading}"
    if any(line.strip() == header_line for line in md_lines):
        return md_lines
    # Add a blank line before new section if needed
    if md_lines and md_lines[-1].strip() != "":
        md_lines.append("\n")
    md_lines.append(header_line + "\n")
    md_lines.append("\n")
    return md_lines


def find_section_bounds(md_lines: List[str], heading: str) -> Tuple[int, int]:
    """
    Return (start_idx, end_idx) bounds for a '## heading' section content.
    start_idx points to the heading line.
    end_idx is the index of the next heading of same or higher level (## or #), or len(md_lines).
    """
    header_line = f"## {heading}"
    start = None
    for i, line in enumerate(md_lines):
        if line.strip() == header_line:
            start = i
            break
    if start is None:
        raise ValueError(f"Section not found: {heading}")

    end = len(md_lines)
    for j in range(start + 1, len(md_lines)):
        stripped = md_lines[j].lstrip()
        if stripped.startswith("## ") or stripped.startswith("# "):
            end = j
            break
    return start, end


def append_bullet_to_section(md_lines: List[str], heading: str, bullet_text: str) -> List[str]:
    """
    Append a bullet "- <bullet_text>" to the end of the specified section,
    unless it already exists (exact match ignoring whitespace).
    """
    md_lines = ensure_section(md_lines, heading)
    start, end = find_section_bounds(md_lines, heading)

    bullet_line = f"- {bullet_text}".strip()

    # Check if already present in section
    existing = {line.strip() for line in md_lines[start:end]}
    if bullet_line in existing:
        return md_lines

    # Insert before end heading (i.e., at end of section)
    insert_at = end
    # Ensure there's a blank line after heading if section is empty
    # (Not strictly necessary, but keeps it readable)
    md_lines.insert(insert_at, bullet_line + "\n")
    return md_lines


def append_log_entry(md_lines: List[str], entry: str) -> List[str]:
    md_lines = ensure_section(md_lines, "Log")
    # Put log entries at end of Log section
    return append_bullet_to_section(md_lines, "Log", entry)


def update_progress(
    progress_path: pathlib.Path,
    log_entry: str,
    done: Optional[List[str]] = None,
    in_progress: Optional[List[str]] = None,
    next_items: Optional[List[str]] = None,
) -> None:
    if progress_path.exists():
        md = progress_path.read_text(encoding="utf-8")
        md_lines = md.splitlines(keepends=True)
    else:
        md_lines = ["# Progress\n", "\n"]

    # Ensure primary sections exist (nice to have)
    for section in ("Done", "In progress", "Next", "Log"):
        md_lines = ensure_section(md_lines, section)

    # Append optional bullets
    for item in done or []:
        md_lines = append_bullet_to_section(md_lines, "Done", item)

    for item in in_progress or []:
        md_lines = append_bullet_to_section(md_lines, "In progress", item)

    for item in next_items or []:
        md_lines = append_bullet_to_section(md_lines, "Next", item)

    md_lines = append_log_entry(md_lines, log_entry)

    write_text(progress_path, "".join(md_lines))


def copy_to_clipboard(text: str) -> None:
    # macOS pbcopy preferred; fallback to xclip/xsel if present.
    if shutil.which("pbcopy"):
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(input=text.encode("utf-8"))
        if p.returncode != 0:
            raise RuntimeError("pbcopy failed")
        return

    if shutil.which("xclip"):
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        p.communicate(input=text.encode("utf-8"))
        if p.returncode != 0:
            raise RuntimeError("xclip failed")
        return

    if shutil.which("xsel"):
        p = subprocess.Popen(["xsel", "--clipboard", "--input"], stdin=subprocess.PIPE)
        p.communicate(input=text.encode("utf-8"))
        if p.returncode != 0:
            raise RuntimeError("xsel failed")
        return

    raise RuntimeError("No clipboard tool found (pbcopy/xclip/xsel)")


def build_prompt(prompt_index: str) -> Tuple[str, pathlib.Path, pathlib.Path]:
    header_path = get_header_path()

    prompt_base = PROMPTS_DIR / prompt_index
    prompt_path = find_existing_file(prompt_base, exts=("", ".md", ".txt"))

    header = normalize_md_newlines(read_text(header_path))
    body = normalize_md_newlines(read_text(prompt_path))

    combined = header + "\n" + body
    return combined, header_path, prompt_path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sm_prompt",
        description="Builds a prompt from docs/10-chat-started.md + docs/prompts/<prompt_index> and updates docs/11-progress.md.",
    )
    parser.add_argument("prompt_index", help="e.g., prompt_2 (maps to docs/prompts/prompt_2[.md])")

    parser.add_argument("--copy", action="store_true", help="Copy the generated prompt to clipboard")
    parser.add_argument("--out", type=str, default="", help="Write generated prompt to this file (optional)")

    # Progress updates
    parser.add_argument("--done", action="append", default=[], help="Append bullet to '## Done' (repeatable)")
    parser.add_argument("--in-progress", dest="in_progress", action="append", default=[], help="Append bullet to '## In progress' (repeatable)")
    parser.add_argument("--next", dest="next_items", action="append", default=[], help="Append bullet to '## Next' (repeatable)")
    parser.add_argument("--no-progress", action="store_true", help="Do not update docs/11-progress.md")

    args = parser.parse_args()

    combined, header_path, prompt_path = build_prompt(args.prompt_index)

    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"{timestamp} — generated prompt '{args.prompt_index}' (header={header_path.name}, prompt={prompt_path.name})"

    if not args.no_progress:
        update_progress(
            PROGRESS_PATH,
            log_entry=log_entry,
            done=args.done,
            in_progress=args.in_progress,
            next_items=args.next_items,
        )

    # Write file if requested
    if args.out:
        out_path = pathlib.Path(args.out).expanduser()
        write_text(out_path, combined)

    # Copy if requested
    if args.copy:
        copy_to_clipboard(combined)

    # Always print to stdout (so you can pipe it)
    sys.stdout.write(combined)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
