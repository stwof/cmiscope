#!/usr/bin/env python3
"""Compare the bundled OIF CMIS 5.3 and 5.4 specification PDFs.

This closes the knowledge-graph open question ``P-02`` (version differences)
with a reproducible, fully automated report.  It reuses the standard-library
PDF reader and the coordinate-based table extractor introduced for the CMIS 5.3
provenance index, so no third-party package and no network access is required.

Outputs:
    data/spec_version_diff.json   machine-readable full diff
    docs/CMIS_53_54_DIFF.md       human-readable summary

Only factual identifiers are persisted (table numbers, short captions, page
numbers, field names, addresses, access types).  Verbatim OIF description text
is never written to disk.  The OIF specification remains authoritative; this
report is a navigation aid, not a compliance statement.  See NOTICE section 8.

Usage:
    python tools/diff_spec_versions.py
    python tools/diff_spec_versions.py --index54 /tmp/54.json --max-examples 30

The 5.3 index is reused when its embedded PDF hash still matches; otherwise it
is rebuilt in memory.  The 5.4 index is parsed in memory by default so the
project does not have to ship a second multi-megabyte index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from parse_spec_pdf import (  # noqa: E402 - path bootstrapped above
    DEFAULT_OUT as DEFAULT_INDEX_53,
    DEFAULT_PDF as DEFAULT_PDF_53,
    DEFAULT_REFERENCE,
    build as build_index,
)

DEFAULT_PDF_54 = ROOT / "knowledge" / "specs" / "OIF-CMIS-05.4.pdf"
DEFAULT_OUT_JSON = ROOT / "data" / "spec_version_diff.json"
DEFAULT_OUT_MD = ROOT / "docs" / "CMIS_53_54_DIFF.md"

COMPARE_ATTRIBUTES = ("access", "value_type", "unit", "scale", "byte_length",
                      "is_reserved")


# --------------------------------------------------------------------------- input helpers

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm(value: str | None) -> str:
    """Case/whitespace-insensitive comparison key for factual identifiers."""
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _loose(value: str | None) -> str:
    """Ignore punctuation and spacing too, to isolate substantive caption edits."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def load_index(pdf: Path, index: Path | None, reference: Path | None,
               version: str) -> tuple[dict, str]:
    """Reuse a cached index only when it was built from this exact PDF."""
    digest = _sha256(pdf)
    if index and index.is_file():
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        meta = data.get("meta", {})
        if meta.get("pdf_sha256") == digest and version in str(meta.get("specification", "")):
            return data, "cached index"
    return build_index(pdf, reference), "parsed PDF"


def _table_map(index: dict) -> dict[str, dict]:
    return {row["table_id"]: row for row in index.get("tables", [])}


def _command_map(index: dict) -> dict[str, dict]:
    return {str(row["cmd_id"]).upper(): row for row in index.get("cdb_commands", [])}


def _field_map(index: dict) -> dict[tuple, dict]:
    return {(row.get("page"), row.get("byte"), _norm(row.get("name"))): row
            for row in index.get("fields", [])}


# --------------------------------------------------------------------------- diff

def _table_key(table_id: str) -> tuple[int, int]:
    section, number = table_id.split("-")
    return int(section), int(number)


def _terminology(value: str | None) -> str:
    """Fold the global 5.3 -> 5.4 wording change before comparing captions."""
    text = (value or "").replace("paged memory modules only",
                                 "not for static memory modules")
    return _loose(text)


def diff_tables(old: dict[str, dict], new: dict[str, dict]) -> dict:
    """Align tables by caption sequence, not by table number.

    CMIS 5.4 inserts tables in the middle of Section 8, so every later table
    is renumbered.  Comparing by ``table_id`` would report hundreds of false
    "renames" and "page shifts"; a SequenceMatcher alignment on captions
    recovers the real insertions, deletions and edits instead.
    """
    def brief(row: dict) -> dict:
        return {key: row.get(key) for key in
                ("table_id", "section", "title", "pdf_page", "field_rows")}

    keys53 = sorted(old, key=_table_key)
    keys54 = sorted(new, key=_table_key)
    matcher = SequenceMatcher(
        None,
        [_loose(old[k].get("title")) for k in keys53],
        [_loose(new[k].get("title")) for k in keys54],
        autojunk=False,
    )

    matched, added, removed, candidates = [], [], [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched.extend(zip(keys53[i1:i2], keys54[j1:j2]))
        elif tag == "insert":
            added.extend(keys54[j1:j2])
        elif tag == "delete":
            removed.extend(keys53[i1:i2])
        else:
            width = min(i2 - i1, j2 - j1)
            candidates.extend(zip(keys53[i1:i1 + width], keys54[j1:j1 + width]))
            added.extend(keys54[j1 + width:j2])
            removed.extend(keys53[i1 + width:i2])

    cosmetic, terminology, renamed, row_changes = [], [], [], []
    for id53, id54 in matched:
        a, b = old[id53], new[id54]
        if _norm(a.get("title")) != _norm(b.get("title")):
            cosmetic.append({"table_id_53": id53, "table_id_54": id54,
                             "title_53": a.get("title"), "title_54": b.get("title")})
        if a.get("field_rows") != b.get("field_rows"):
            row_changes.append({"table_id_53": id53, "table_id_54": id54,
                                "field_rows_53": a.get("field_rows"),
                                "field_rows_54": b.get("field_rows")})
    for id53, id54 in candidates:
        a, b = old[id53].get("title"), new[id54].get("title")
        entry = {"table_id_53": id53, "table_id_54": id54,
                 "title_53": a, "title_54": b}
        if _loose(a) == _loose(b):
            cosmetic.append(entry)
        elif _terminology(a) == _terminology(b):
            entry["kind"] = "terminology"
            terminology.append(entry)
        else:
            entry["kind"] = "substantive"
            renamed.append(entry)

    number_deltas = [int(y.split("-")[1]) - int(x.split("-")[1])
                     for x, y in matched if x.split("-")[0] == y.split("-")[0]]
    page_deltas = [(new[y].get("pdf_page") or 0) - (old[x].get("pdf_page") or 0)
                   for x, y in matched]
    dominant_number = (Counter(number_deltas).most_common(1)[0][0]
                       if number_deltas else 0)
    modal_page = Counter(page_deltas).most_common(1)[0][0] if page_deltas else 0
    return {
        "count_53": len(old), "count_54": len(new),
        "alignment": {
            "method": "difflib.SequenceMatcher on normalized table captions",
            "matched_pairs": len(matched),
            "dominant_number_shift": dominant_number,
            "tables_with_dominant_number_shift": sum(
                1 for d in number_deltas if d == dominant_number),
            "note": ("CMIS 5.4 inserts tables in the middle of Section 8; later "
                     "tables are renumbered. Table IDs are therefore NOT stable "
                     "across versions and must not be compared directly."),
        },
        "added": [brief(new[t]) for t in sorted(added, key=_table_key)],
        "removed": [brief(old[t]) for t in sorted(removed, key=_table_key)],
        "renamed": renamed,
        "terminology_updates": terminology,
        "cosmetic_title_changes": cosmetic,
        "page_shift": {
            "min_delta": min(page_deltas) if page_deltas else 0,
            "max_delta": max(page_deltas) if page_deltas else 0,
            "modal_delta": modal_page,
            "tables_with_modal_delta": sum(1 for d in page_deltas if d == modal_page),
            "note": ("PDF physical page numbers of matched tables. Inserted "
                     "chapters shift most pages; this is layout, not content."),
        },
        "field_row_changes": row_changes,
    }


def diff_commands(old: dict[str, dict], new: dict[str, dict]) -> dict:
    def brief(row: dict) -> dict:
        return {key: row.get(key) for key in
                ("cmd_id", "title", "spec_section", "detail_table", "pdf_page")}

    common = old.keys() & new.keys()
    changed: list[dict] = []
    for cmd_id in sorted(common):
        a, b = old[cmd_id], new[cmd_id]
        deltas = {key: {"53": a.get(key), "54": b.get(key)}
                  for key in ("title", "spec_section", "detail_table")
                  if _norm(str(a.get(key) or "")) != _norm(str(b.get(key) or ""))}
        if deltas:
            changed.append({"cmd_id": cmd_id, "changes": deltas})
    return {
        "count_53": len(old), "count_54": len(new),
        "added": [brief(new[c]) for c in sorted(new.keys() - old.keys())],
        "removed": [brief(old[c]) for c in sorted(old.keys() - new.keys())],
        "changed": changed,
    }


def diff_fields(old: dict[tuple, dict], new: dict[tuple, dict]) -> dict:
    def brief(row: dict) -> dict:
        return {key: row.get(key) for key in
                ("table_id", "page", "byte", "name", "byte_length", "access",
                 "value_type", "pdf_page")}

    common = old.keys() & new.keys()
    changed = []
    for key in sorted(common, key=lambda k: (str(k[0]), k[1] if isinstance(k[1], int) else -1,
                                            str(k[2]))):
        deltas = {attr: {"53": old[key].get(attr), "54": new[key].get(attr)}
                  for attr in COMPARE_ATTRIBUTES
                  if str(old[key].get(attr) or "") != str(new[key].get(attr) or "")}
        if deltas:
            changed.append({"page": key[0], "byte": key[1], "name": old[key].get("name"),
                            "changes": deltas})
    return {
        "count_53": len(old), "count_54": len(new),
        "added": [brief(new[k]) for k in sorted(
            new.keys() - old.keys(),
            key=lambda k: (str(k[0]), k[1] if isinstance(k[1], int) else -1, str(k[2])))],
        "removed": [brief(old[k]) for k in sorted(
            old.keys() - new.keys(),
            key=lambda k: (str(k[0]), k[1] if isinstance(k[1], int) else -1, str(k[2])))],
        "changed": changed,
        "caveat": ("Field rows come from best-effort coordinate reconstruction and are "
                   "incomplete by design; treat these entries as review candidates, not "
                   "as statements about the specification. The published CSV and the OIF "
                   "PDF are authoritative."),
    }


def build_diff(old_index: dict, new_index: dict, sources: dict) -> dict:
    tables = diff_tables(_table_map(old_index), _table_map(new_index))
    commands = diff_commands(_command_map(old_index), _command_map(new_index))
    fields = diff_fields(_field_map(old_index), _field_map(new_index))
    return {
        "meta": {
            "generator": "tools/diff_spec_versions.py",
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "versions": sources,
            "reader": "tools/spec_pdf.py (Python standard library only)",
            "content_policy": ("Only factual identifiers are persisted; verbatim OIF "
                               "description text is not written to disk."),
            "authority_note": ("The OIF specification is authoritative. This is a "
                               "navigation aid for knowledge-graph item P-02, not a "
                               "compliance statement."),
        },
        "summary": {
            "tables": {"count_53": tables["count_53"], "count_54": tables["count_54"],
                       "added": len(tables["added"]), "removed": len(tables["removed"]),
                       "renamed": len(tables["renamed"]),
                       "terminology_updates": len(tables["terminology_updates"]),
                       "cosmetic_title_changes": len(tables["cosmetic_title_changes"]),
                       "alignment": tables["alignment"],
                       "page_shift": tables["page_shift"]},
            "cdb_commands": {"count_53": commands["count_53"],
                             "count_54": commands["count_54"],
                             "added": len(commands["added"]),
                             "removed": len(commands["removed"]),
                             "changed": len(commands["changed"])},
            "fields_indicative": {"count_53": fields["count_53"],
                                  "count_54": fields["count_54"],
                                  "added": len(fields["added"]),
                                  "removed": len(fields["removed"]),
                                  "changed": len(fields["changed"])},
        },
        "tables": tables,
        "cdb_commands": commands,
        "fields_indicative": fields,
    }


# --------------------------------------------------------------------------- markdown

def _cell(value) -> str:
    text = "—" if value in (None, "") else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_（无）_\n"
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(out) + "\n"


def render_markdown(diff: dict, limit: int) -> str:
    s, t, c, f = diff["summary"], diff["tables"], diff["cdb_commands"], diff["fields_indicative"]
    v = diff["meta"]["versions"]
    lines = [
        "# OIF CMIS 5.3 → 5.4 规范差异报告",
        "",
        f"> 由 `tools/diff_spec_versions.py` 自动生成于 "
        f"`{diff['meta']['generated_at']}`。知识图谱待确认项 **P-02**（版本差异）的自动化依据。",
        "",
        "## 1. 输入与结论",
        "",
        "| 项 | CMIS 5.3 | CMIS 5.4 |",
        "| --- | --- | --- |",
        f"| PDF | `{v['53']['pdf_file']}` | `{v['54']['pdf_file']}` |",
        f"| 页数 | {v['53']['pdf_pages']} | {v['54']['pdf_pages']} |",
        f"| SHA-256（前 12 位） | `{v['53']['pdf_sha256'][:12]}` | `{v['54']['pdf_sha256'][:12]}` |",
        f"| 索引来源 | {v['53']['source']} | {v['54']['source']} |",
        f"| 表 / CDB 命令 | {t['count_53']} / {c['count_53']} | {t['count_54']} / {c['count_54']} |",
        "",
        f"**表目录（按标题序列对齐）**：5.4 真正新增 {s['tables']['added']} 张、"
        f"移除 {s['tables']['removed']} 张、实质改名 {s['tables']['renamed']} 张、"
        f"术语统一替换 {s['tables']['terminology_updates']} 张、"
        f"仅标点/空格差异 {s['tables']['cosmetic_title_changes']} 张。"
        f"**CDB 命令**：新增 {s['cdb_commands']['added']} 条、"
        f"移除 {s['cdb_commands']['removed']} 条、属性变化 {s['cdb_commands']['changed']} 条。",
        "",
        f"> ⚠️ **表号不能直接对比**：5.4 在 Section 8 中段插入了表格，"
        f"{s['tables']['alignment']['matched_pairs']} 张按标题成功配对的表中，有 "
        f"**{s['tables']['alignment']['tables_with_dominant_number_shift']} 张的表号整体 "
        f"{s['tables']['alignment']['dominant_number_shift']:+d}**；页码位移 "
        f"{s['tables']['page_shift']['min_delta']:+d} ~ "
        f"{s['tables']['page_shift']['max_delta']:+d} 页属排版效应。"
        f"本报告用 `difflib.SequenceMatcher` 对齐标题序列后再比对，避免把重编号误报为改动。",
        "",
        "## 2. 新增表（5.4 独有）",
        "",
        _md_table(["表号", "标题", "PDF 页", "字段行"],
                  [[r["table_id"], r["title"], r["pdf_page"], r["field_rows"]]
                   for r in t["added"][:limit]]),
        (f"_仅列出前 {limit} 条，完整清单见 `data/spec_version_diff.json`。_\n"
         if len(t["added"]) > limit else ""),
        "## 3. 移除表（仅 5.3）",
        "",
        _md_table(["表号", "标题", "PDF 页", "字段行"],
                  [[r["table_id"], r["title"], r["pdf_page"], r["field_rows"]]
                   for r in t["removed"][:limit]]),
        (f"_仅列出前 {limit} 条。_\n" if len(t["removed"]) > limit else ""),
        "## 4. 表标题变化（实质，忽略大小写/标点/空格差异）",
        "",
        _md_table(["5.3 表号", "5.4 表号", "5.3 标题", "5.4 标题"],
                  [[r["table_id_53"], r["table_id_54"], r["title_53"], r["title_54"]]
                   for r in t["renamed"][:limit]]),
        (f"_仅列出前 {limit} 条，共 {len(t['renamed'])} 条。_\n"
         if len(t["renamed"]) > limit else ""),
        "## 4b. 术语统一替换（5.3 → 5.4 全局措辞变化）",
        "",
        "> 5.4 以「not for static memory modules」替换 5.3 的 "
        "「paged memory modules only」，属于全局措辞调整，单列以免淹没实质改名。",
        "",
        _md_table(["5.3 表号", "5.4 表号", "5.3 标题", "5.4 标题"],
                  [[r["table_id_53"], r["table_id_54"], r["title_53"], r["title_54"]]
                   for r in t["terminology_updates"][:limit]]),
        (f"_仅列出前 {limit} 条，共 {len(t['terminology_updates'])} 条。_\n"
         if len(t["terminology_updates"]) > limit else ""),
        "## 4c. 重编号与页码位移",
        "",
        _md_table(["指标", "值"],
                  [["对齐方法", s["tables"]["alignment"]["method"]],
                   ["按标题配对的表", s["tables"]["alignment"]["matched_pairs"]],
                   ["主流表号位移", f"{s['tables']['alignment']['dominant_number_shift']:+d} "
                    f"({s['tables']['alignment']['tables_with_dominant_number_shift']} 张表)"],
                   ["页码位移范围", f"{s['tables']['page_shift']['min_delta']:+d} ~ "
                    f"{s['tables']['page_shift']['max_delta']:+d} 页"],
                   ["最常见页码位移", f"{s['tables']['page_shift']['modal_delta']:+d} 页 "
                    f"({s['tables']['page_shift']['tables_with_modal_delta']} 张表)"]]),
        "",
        "## 5. CDB 命令变化",
        "",
        "**新增命令**",
        "",
        _md_table(["CMD ID", "标题", "条款", "明细表", "PDF 页"],
                  [[r["cmd_id"], r["title"], r["spec_section"], r["detail_table"],
                    r["pdf_page"]] for r in c["added"][:limit]]),
        "**移除命令**",
        "",
        _md_table(["CMD ID", "标题", "条款", "明细表", "PDF 页"],
                  [[r["cmd_id"], r["title"], r["spec_section"], r["detail_table"],
                    r["pdf_page"]] for r in c["removed"][:limit]]),
        "**属性变化**",
        "",
        _md_table(["CMD ID", "变化字段", "5.3", "5.4"],
                  [[r["cmd_id"], key, pair["53"], pair["54"]]
                   for r in c["changed"][:limit]
                   for key, pair in r["changes"].items()]),
        (f"_仅列出前 {limit} 条。_\n"
         if max(len(c["added"]), len(c["removed"]), len(c["changed"])) > limit else ""),
        "> `detail_table` 的变化大多来自上述表号重编号（5.4 中普遍 +2 / +10），"
        "不代表命令语义改变；`title` 与 `spec_section` 的变化才需要人工复核。",
        "",
        "## 6. 字段级差异（指示性，需人工复核）",
        "",
        f"按 `(page, byte, name)` 对齐：5.3 抽取 {f['count_53']} 行、5.4 抽取 "
        f"{f['count_54']} 行；新增 {s['fields_indicative']['added']}、移除 "
        f"{s['fields_indicative']['removed']}、属性变化 {s['fields_indicative']['changed']}。",
        "",
        "> ⚠️ 字段行来自坐标重建，覆盖率不完整（5.3 相对 CSV 约 91.5%），因此这些差异"
        "**只作为复核线索**，不能据此断言规范增删。逐条结论必须回到 OIF 原文；字段值以"
        " `data/cmis53_reference.json`（源自上游 CSV）为准。",
        "",
        _md_table(["页", "Byte", "字段", "表号", "access", "value_type"],
                  [[r["page"], r["byte"], r["name"], r["table_id"],
                    r.get("access"), r.get("value_type")]
                   for r in f["added"][:10]]),
        "## 7. 复现与边界",
        "",
        "```bash",
        "python tools/parse_spec_pdf.py                 # 重建 5.3 索引（可选）",
        "python tools/diff_spec_versions.py            # 生成本报告 + JSON 差异",
        "python tools/test_spec_diff.py                # 报告回归测试",
        "```",
        "",
        "- 纯 Python 标准库，无 `pdfplumber` / `openpyxl`，无网络访问；"
        "5.3 索引仅在 PDF SHA-256 匹配时复用，否则自动重新解析。",
        "- 只持久化事实标识（表号、短标题、页码、字段名、地址、access），"
        "**不写入 OIF 描述正文**。版权与许可边界见 `NOTICE` 第 8 节和 "
        "`knowledge/specs/README.md`。",
        "- 页码为 PDF 物理页；5.4 表号与 5.3 相同不代表内容相同，请结合标题变化判断。",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- entry point

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf53", type=Path, default=DEFAULT_PDF_53)
    parser.add_argument("--pdf54", type=Path, default=DEFAULT_PDF_54)
    parser.add_argument("--index53", type=Path, default=DEFAULT_INDEX_53,
                        help="cached 5.3 index; rebuilt when its PDF hash does not match")
    parser.add_argument("--index54", type=Path, default=None,
                        help="optional cached 5.4 index; the PDF is parsed in memory otherwise")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE,
                        help="5.3 CSV-derived reference used only when rebuilding the 5.3 index")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--max-examples", type=int, default=20,
                        help="max rows shown per Markdown table (default: 20)")
    args = parser.parse_args()

    def resolve(p: Path | None) -> Path | None:
        if p is None:
            return None
        return (p if p.is_absolute() else ROOT / p).resolve()

    pdf53, pdf54 = resolve(args.pdf53), resolve(args.pdf54)
    for path in (pdf53, pdf54):
        if not path.is_file():
            print(f"ERROR: specification PDF not found: {path}", file=sys.stderr)
            return 1
    reference = resolve(args.reference)
    reference = reference if reference and reference.is_file() else None

    old, src53 = load_index(pdf53, resolve(args.index53), reference, "05.3")
    new, src54 = load_index(pdf54, resolve(args.index54), None, "05.4")

    sources = {}
    for key, index, path, source in (("53", old, pdf53, src53), ("54", new, pdf54, src54)):
        meta = index.get("meta", {})
        sources[key] = {
            "specification": meta.get("specification"),
            "pdf_file": str(path.relative_to(ROOT)).replace("\\", "/")
            if path.is_relative_to(ROOT) else str(path),
            "pdf_sha256": _sha256(path),
            "pdf_pages": meta.get("pdf_pages"),
            "source": source,
            "tables": len(index.get("tables", [])),
            "field_rows": len(index.get("fields", [])),
            "cdb_commands": len(index.get("cdb_commands", [])),
        }

    diff = build_diff(old, new, sources)
    out_json, out_md = resolve(args.out_json), resolve(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_bytes((json.dumps(diff, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    out_md.write_bytes(render_markdown(diff, max(1, args.max_examples)).encode("utf-8"))

    s = diff["summary"]
    print(f"Wrote {out_json} ({out_json.stat().st_size:,} bytes)")
    print(f"Wrote {out_md} ({out_md.stat().st_size:,} bytes)")
    print(f"  sources: 5.3={src53}, 5.4={src54}")
    print(f"  tables: {s['tables']['count_53']} -> {s['tables']['count_54']} "
          f"(+{s['tables']['added']}/-{s['tables']['removed']}, "
          f"renamed={s['tables']['renamed']}, "
          f"terminology={s['tables']['terminology_updates']}, "
          f"cosmetic={s['tables']['cosmetic_title_changes']}, "
          f"aligned={s['tables']['alignment']['matched_pairs']}, "
          f"renumbered={s['tables']['alignment']['dominant_number_shift']:+d})")
    print(f"  cdb: {s['cdb_commands']['count_53']} -> {s['cdb_commands']['count_54']} "
          f"(+{s['cdb_commands']['added']}/-{s['cdb_commands']['removed']}, "
          f"changed={s['cdb_commands']['changed']})")
    print(f"  fields (indicative): +{s['fields_indicative']['added']}/"
          f"-{s['fields_indicative']['removed']}/~{s['fields_indicative']['changed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
