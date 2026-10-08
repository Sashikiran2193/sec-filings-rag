"""Turn raw 10-K HTML into clean text, one file per 10-K item.

Usage:
  python parse_10k.py <path to raw .htm>   parse one filing
  python parse_10k.py                      parse every filing under data/raw/

Reads data/raw/<ticker>/<year>/<file>.htm and writes
data/clean/<ticker>/<year>/item_<n>.txt (e.g. item_1a.txt, item_7.txt).

Known limit: tables are flattened to text, one row per line with cells
separated by " | ". "$" is removed from table amounts and "%" is joined to
its number, so each value sits in one cell. Column alignment, merged cells and
multi-row headers are lost, so financial tables read roughly but not reliably.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/clean")

SKIP_TAGS = {"script", "style", "head", "title", "ix:header"}
VOID_TAGS = {"br", "hr", "img", "meta", "link", "input", "col", "area", "base", "wbr"}
BLOCK_TAGS = {
    "p", "div", "br", "hr", "li", "ul", "ol", "table", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "blockquote",
}
HIDDEN_STYLE = re.compile(r"display\s*:\s*none", re.IGNORECASE)
AMOUNT = re.compile(r"^\(?[\d.,]+\)?$|^[—–-]$")  # 1,234  (56)  0.5  — (zero)


class TextExtractor(HTMLParser):
    """Collect visible text, dropping scripts, styling and hidden XBRL blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[bool] = []  # True for each open tag whose content is skipped
        self.tags: list[str] = []

    @property
    def skipping(self) -> bool:
        return any(self.stack)

    def line_break(self, tag):
        """Start a new line for a block tag; inside a table cell, just a space."""
        if tag not in BLOCK_TAGS or self.skipping:
            return
        in_cell = "td" in self.tags or "th" in self.tags
        self.parts.append(" " if in_cell and tag not in ("tr", "table") else "\n")

    def handle_starttag(self, tag, attrs):
        self.line_break(tag)
        if tag in VOID_TAGS:
            return
        style = dict(attrs).get("style") or ""
        self.tags.append(tag)
        self.stack.append(tag in SKIP_TAGS or bool(HIDDEN_STYLE.search(style)))

    def handle_startendtag(self, tag, attrs):
        self.line_break(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS or tag not in self.tags:
            return
        while self.tags:
            self.stack.pop()
            if self.tags.pop() == tag:
                break
        if self.skipping:
            return
        if tag in ("td", "th"):
            self.parts.append(" | ")
        else:
            self.line_break(tag)

    def handle_data(self, data):
        if not self.skipping:
            # Newlines in the HTML source are just spacing; real breaks come from block tags.
            self.parts.append(re.sub(r"\s+", " ", data))


def clean_cells(cells: list[str]) -> list[str]:
    """Drop empty and "$" cells, strip "$" off amounts, and join "%" onto its number.

    Filings put "$" and "%" in cells of their own, which shifts the numbers
    into the wrong columns: "$ | 65,821 | ... | (9) | %" becomes "65,821 | ... | (9)%".
    In header rows ("2024 | $ | %") they are column labels and are kept.
    """
    cells = [c for c in cells if c]
    out: list[str] = []
    for i, cell in enumerate(cells):
        nxt = cells[i + 1] if i + 1 < len(cells) else ""
        if cell == "$" and (AMOUNT.match(nxt) or nxt[:1].isdigit()):  # also "0.83 – 0.91"
            continue
        if cell in ("%", "%)") and out and AMOUNT.match(out[-1]) and cells[i - 1] != "$":
            out[-1] += cell
            continue
        bare = re.sub(r"^\$\s*", "", cell)
        out.append(bare if AMOUNT.match(bare) else cell)
    return out


def clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()  # \s also matches non-breaking spaces
    if "|" in line:  # table row
        line = " | ".join(clean_cells([c.strip() for c in line.split("|")]))
    return line


def html_to_text(raw: str) -> str:
    parser = TextExtractor()
    parser.feed(raw)
    parser.close()
    lines = (clean_line(l) for l in "".join(parser.parts).splitlines())
    return "\n".join(l for l in lines if l)


# "Item 1A." / "ITEM 7 —" / "Item 9C:" at the start of a line.
ITEM_HEADING = re.compile(r"^item\s+(\d{1,2}[a-c]?)\b\s*[.:\-—–]?", re.IGNORECASE | re.MULTILINE)
ITEM_ORDER = [
    "1", "1a", "1b", "1c", "2", "3", "4", "4a",
    "5", "6", "7", "7a", "8", "9", "9a", "9b", "9c",
    "10", "11", "12", "13", "14", "15", "16",
]
# Lines repeated on every page: "12", "PART II", "Item 7", "Item 1B, 1C",
# "Item 1. Business (Continued)".
PAGE_NOISE = re.compile(
    r"^(\d{1,3}|part [iv]+\.?|item [\d a-c,]+|item .*\(continued\))$", re.IGNORECASE
)


def split_items(text: str) -> dict[str, str]:
    """Split filing text into {item number: section text}.

    Headings appear first in the table of contents, then again where each
    section starts, and some filings repeat them as page headers. So the body
    is taken to start at the first "Item 1" after the TOC's "Item 2", and from
    there each item starts at its first heading after the previous item's.
    """
    matches = [(m.group(1).lower(), m.start()) for m in ITEM_HEADING.finditer(text)]
    matches = [(item, pos) for item, pos in matches if item in ITEM_ORDER]

    first = {}
    for item, pos in matches:
        first.setdefault(item, pos)
    pos = 0
    if "1" in first and "2" in first and first["2"] > first["1"]:
        pos = first["2"]  # skip past the table of contents

    starts = []
    for item in ITEM_ORDER:
        nxt = next((p for i, p in matches if i == item and p > pos), None)
        if nxt is not None:
            starts.append((item, nxt))
            pos = nxt

    sections = {}
    for (item, start), (_, end) in zip(starts, starts[1:] + [(None, len(text))]):
        lines = text[start:end].strip().splitlines()
        sections[item] = "\n".join(l for l in lines if not PAGE_NOISE.match(l))
    return sections


def parse_filing(raw_path: Path) -> Path:
    """Write one clean text file per item; return the output directory."""
    ticker, year = raw_path.parent.parent.name, raw_path.parent.name
    text = html_to_text(raw_path.read_text(encoding="utf-8", errors="replace"))

    out_dir = CLEAN_DIR / ticker / year
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("item_*.txt"):
        old.unlink()
    for item, section in split_items(text).items():
        (out_dir / f"item_{item}.txt").write_text(section + "\n", encoding="utf-8")
    return out_dir


if __name__ == "__main__":
    if len(sys.argv) == 2:
        paths = [Path(sys.argv[1])]
    elif len(sys.argv) == 1:
        paths = sorted(RAW_DIR.glob("*/*/*.htm"))
    else:
        sys.exit("Usage: python parse_10k.py [<path to raw .htm>]")
    for path in paths:
        out_dir = parse_filing(path)
        print(f"{path} -> {out_dir} ({len(list(out_dir.glob('item_*.txt')))} items)")
