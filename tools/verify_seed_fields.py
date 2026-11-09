#!/usr/bin/env python3
"""Cross-check CMIScope's 64 demo fields against the CMIS 5.3 reference table.

``data/seed.json`` contains synthetic demo fields whose byte offsets were
flagged as "pending confirmation" in knowledge-graph item ``P-01``.  The
read-only reference layer (``data/cmis53_reference.json``, 2442 authoritative
rows derived from jimfred/CMIS) now makes those offsets checkable offline.

This tool is **advisory only**: it never edits ``seed.json`` and never feeds
values into the hardware write path.  It produces:
    data/seed_field_verification.json   full per-field result
    docs/SEED_FIELD_VERIFICATION.md    review checklist for P-01

Matching is performed in three stages (exact name -> exact address -> fuzzy
name) because the demo dataset uses hand-written ``field_key`` aliases rather
than canonical CMIS register names.  Fuzzy results are always labelled
``candidate`` and require human confirmation against the OIF specification.

Usage:
    python tools/verify_seed_fields.py
    python tools/verify_seed_fields.py --strict     # exit 1 on address/page mismatch
    python tools/verify_seed_fields.py --seed data/seed.json --reference data/cmis53_reference.json

The OIF specification is authoritative; see NOTICE and
docs/CMIS53_REFERENCE.md for the mixed-license boundary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = ROOT / "data" / "seed.json"
DEFAULT_REFERENCE = ROOT / "data" / "cmis53_reference.json"
DEFAULT_OUT_JSON = ROOT / "data" / "seed_field_verification.json"
DEFAULT_OUT_MD = ROOT / "docs" / "SEED_FIELD_VERIFICATION.md"

_HEX_PAREN = re.compile(r"0x([0-9A-Fa-f]{1,3})\b")
_HEX_SUFFIX = re.compile(r"^\s*([0-9A-Fa-f]{1,3})h\b", re.I)
_DECIMAL = re.compile(r"\b(\d{1,3})\b")
_PAGE_HEX = re.compile(r"^([0-9A-Fa-f]{2})h$", re.I)
_PAGE_RANGE = re.compile(r"^([0-9A-Fa-f]{2})h-([0-9A-Fa-f]{2})h$", re.I)
_PLACEHOLDER = re.compile(r"pending|banked|staged|reply|unknown|tbd", re.I)
_FUZZY_CUTOFF = 0.62

# The demo model uses coarse display types; the reference uses physical types.
_TYPE_EQUIVALENT = {
    "hex": {"hex", "int", "bool", "enum", "text"},
    "int": {"int", "hex", "bool", "float"},
    "float": {"float", "int", "hex"},
    "bool": {"bool", "hex", "enum"},
    "enum": {"enum", "hex", "bool"},
    "ascii": {"ascii", "text"},
    "text": {"text", "ascii", "hex"},
}


# --------------------------------------------------------------------------- normalization

def norm_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def norm_pages(raw: str | None) -> list[str]:
    """Map demo page labels onto reference page identifiers.

    ``Lower`` -> ``Lwr``; ``Lower/11h`` -> two pages; ``A0h-AFh`` -> a range.
    Unrecognised labels are preserved so they surface as unresolved.
    """
    pages: list[str] = []
    for token in re.split(r"[/,;]", raw or ""):
        token = token.strip()
        if not token:
            continue
        if token.casefold() in {"lower", "lwr", "lower memory", "lower page"}:
            pages.append("Lwr")
            continue
        match = _PAGE_RANGE.fullmatch(token)
        if match:
            low, high = int(match.group(1), 16), int(match.group(2), 16)
            pages.extend(f"{n:02X}h" for n in range(low, high + 1))
            continue
        match = _PAGE_HEX.fullmatch(token)
        pages.append(f"{int(match.group(1), 16):02X}h" if match else token)
    return pages


def seed_byte(raw: str | None) -> int | None:
    """Best-effort first byte of a demo address such as ``85 (0x55)``."""
    text = (raw or "").strip()
    if not text or _PLACEHOLDER.search(text):
        return None
    match = _HEX_PAREN.search(text)
    if match:
        return int(match.group(1), 16)
    match = _HEX_SUFFIX.match(text)
    if match:
        return int(match.group(1), 16)
    match = _DECIMAL.search(text)
    return int(match.group(1)) if match else None


def norm_access(value: str | None) -> str:
    """``RO/CoR``, ``RW/...`` etc. keep their primary access mode."""
    return (value or "").split("/")[0].strip().upper()


def similarity(left: str, right: str) -> float:
    return round(SequenceMatcher(None, norm_name(left), norm_name(right),
                                 autojunk=False).ratio(), 3)


# --------------------------------------------------------------------------- matching

def brief(row: dict) -> dict:
    return {key: row.get(key) for key in
            ("key_id", "name", "page", "byte", "byte_length", "access",
             "data_type", "value_type", "ref_table", "ref_section",
             "spec_pdf_page")}


def pick(candidates: list[dict], pages: list[str], byte: int | None) -> dict | None:
    """Prefer rows sharing the demo page, then the demo byte address."""
    if not candidates:
        return None
    def score(row: dict) -> tuple:
        return (1 if row.get("page") in pages else 0,
                1 if byte is not None and row.get("byte") == byte else 0,
                -abs((row.get("byte") or 0) - byte) if byte is not None else 0)
    return max(candidates, key=score)


def classify(field: dict, by_name: dict, by_address: dict,
             name_pool: list[str], name_rows: dict[str, list[dict]]) -> dict:
    key = field.get("field_key") or ""
    pages = norm_pages(field.get("page"))
    byte = seed_byte(field.get("byte_offset"))
    notes: list[str] = []

    match_kind, matched, candidates = "none", None, []
    exact = by_name.get(norm_name(key), [])
    if exact:
        match_kind = "exact_name"
        matched = pick(exact, pages, byte)
        candidates = exact
    elif byte is not None:
        address_hits = [row for page in pages for row in by_address.get((page, byte), [])]
        if address_hits:
            match_kind = "exact_address"
            matched = max(address_hits, key=lambda row: similarity(key, row.get("name")))
            candidates = address_hits
    if matched is None:
        fuzzy = get_close_matches(norm_name(key), name_pool, n=4, cutoff=_FUZZY_CUTOFF)
        fuzzy_rows = [row for name in fuzzy for row in name_rows[name]]
        if fuzzy_rows:
            match_kind = "fuzzy_name"
            matched = max(fuzzy_rows,
                          key=lambda row: (1 if row.get("page") in pages else 0,
                                           similarity(key, row.get("name"))))
            candidates = fuzzy_rows

    result = {
        "field_key": key,
        "page_raw": field.get("page"),
        "pages_normalized": pages,
        "byte_offset_raw": field.get("byte_offset"),
        "byte_offset_parsed": byte,
        "section": field.get("section"),
        "demo_access": field.get("access"),
        "demo_data_type": field.get("data_type"),
        "match_kind": match_kind,
        "reference": brief(matched) if matched else None,
        "candidates": [brief(row) for row in candidates[:3]],
        "checks": {},
        "notes": notes,
        "status": "unresolved",
    }
    if not matched:
        notes.append("No reference row matched by name or address; demo-only field.")
        return result

    ref = matched
    page_ok = ref.get("page") in pages
    byte_ok = byte is None or ref.get("byte") == byte
    access_ok = (norm_access(field.get("access")) == norm_access(ref.get("access"))
                 or not ref.get("access"))
    equivalent = _TYPE_EQUIVALENT.get((field.get("data_type") or "").lower(), set())
    type_ok = not equivalent or (ref.get("data_type") or "").lower() in equivalent
    score = similarity(key, ref.get("name"))
    if match_kind in ("exact_address", "fuzzy_name"):
        # 0.82 keeps borderline look-alikes (e.g. ModuleVoltage/ModuleState)
        # out of the "actionable" bucket.
        confidence = ("high" if score >= 0.82 and page_ok else
                      "medium" if score >= 0.60 else "low")
    else:
        # Exact name match: provenance is certain regardless of string similarity.
        confidence = "exact"
    result["checks"] = {"page_match": page_ok, "byte_match": byte_ok,
                        "access_match": access_ok, "type_compatible": type_ok,
                        "name_similarity": score, "confidence": confidence}
    if not access_ok:
        notes.append(f"access differs: demo={field.get('access')} reference={ref.get('access')}")
    if not type_ok:
        notes.append(f"data type differs: demo={field.get('data_type')} "
                     f"reference={ref.get('data_type')}")

    if match_kind == "exact_name":
        if not page_ok:
            result["status"] = "mismatch"
            notes.append(f"page differs: demo={pages} reference={ref.get('page')}")
        elif byte is None:
            result["status"] = "address_resolved"
            notes.append("Demo offset is pending; reference byte can be used for review.")
        elif not byte_ok:
            result["status"] = "mismatch"
            notes.append(f"byte differs: demo={byte} reference={ref.get('byte')}")
        else:
            result["status"] = "verified"
    else:
        result["status"] = "candidate"
        notes.append("Alias/address-based match only; confirm against OIF text before reuse.")
        if match_kind == "exact_address" and score < 0.5:
            notes.append("Names are unrelated: this is an address coincidence, "
                         "not an alias. Do not reuse without OIF confirmation.")
        if confidence == "low":
            notes.append("Low confidence candidate; treat as unresolved for P-01.")
        if byte is not None and not byte_ok:
            notes.append(f"candidate byte differs: demo={byte} reference={ref.get('byte')}")
    return result


def build_report(seed: dict, reference: dict) -> dict:
    fields = seed.get("fields", [])
    rows = reference.get("fields", [])
    by_name: dict[str, list[dict]] = {}
    by_address: dict[tuple, list[dict]] = {}
    name_rows: dict[str, list[dict]] = {}
    for row in rows:
        name = norm_name(row.get("name"))
        by_name.setdefault(name, []).append(row)
        name_rows.setdefault(name, []).append(row)
        by_address.setdefault((row.get("page"), row.get("byte")), []).append(row)
    name_pool = sorted({name for name in by_name if name})

    results = [classify(field, by_name, by_address, name_pool, name_rows)
               for field in fields]
    status_counts = Counter(r["status"] for r in results)
    kind_counts = Counter(r["match_kind"] for r in results)
    section_counts = {section: dict(Counter(r["status"] for r in results
                                            if r["section"] == section))
                      for section in sorted({r["section"] for r in results if r["section"]})}
    return {
        "meta": {
            "generator": "tools/verify_seed_fields.py",
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "seed_fields": len(fields),
            "reference_fields": len(rows),
            "reference_source": "data/cmis53_reference.json (jimfred/CMIS CSV, OIF-derived)",
            "knowledge_graph_item": "P-01 (register byte offsets)",
            "matching": "exact_name -> exact_address -> fuzzy_name",
            "policy": ("Advisory only: seed.json is never modified and no value enters "
                       "the hardware write path. OIF specification is authoritative."),
            "license_note": ("Field names/addresses are OIF-copyright factual identifiers; "
                             "see NOTICE sections 5-8."),
        },
        "summary": {
            "total": len(results),
            "by_status": dict(sorted(status_counts.items())),
            "by_match_kind": dict(sorted(kind_counts.items())),
            "by_section": section_counts,
            "addressable_demo_fields": sum(1 for r in results
                                           if r["byte_offset_parsed"] is not None),
            "pending_offsets": sum(1 for r in results if r["byte_offset_parsed"] is None),
            "resolvable_offsets": status_counts["address_resolved"],
            "mismatches": status_counts["mismatch"],
            "candidate_confidence": dict(sorted(Counter(
                r["checks"].get("confidence", "n/a") for r in results
                if r["status"] == "candidate").items())),
            "high_confidence_pending_candidates": sum(
                1 for r in results if r["status"] == "candidate"
                and r["byte_offset_parsed"] is None
                and r["checks"].get("confidence") == "high"),
        },
        "fields": results,
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


def render_markdown(report: dict) -> str:
    s = report["summary"]
    results = report["fields"]
    resolved = [r for r in results if r["status"] == "address_resolved"]
    mismatch = [r for r in results if r["status"] == "mismatch"]
    verified = [r for r in results if r["status"] == "verified"]
    candidates = [r for r in results if r["status"] == "candidate"]
    unresolved = [r for r in results if r["status"] == "unresolved"]
    high_pending = [r for r in candidates if r["byte_offset_parsed"] is None
                    and r["checks"].get("confidence") == "high"]

    def row(r: dict) -> list:
        ref = r["reference"] or {}
        return [r["field_key"], r["page_raw"], r["byte_offset_raw"],
                ref.get("page"), ref.get("byte"), ref.get("key_id"),
                ref.get("ref_table"), ref.get("spec_pdf_page")]

    def confidence_row(r: dict) -> list:
        return row(r) + [r["checks"].get("confidence"),
                         r["checks"].get("name_similarity")]

    lines = [
        "# 演示字段与 CMIS 5.3 权威表对照报告",
        "",
        f"> 由 `tools/verify_seed_fields.py` 自动生成于 "
        f"`{report['meta']['generated_at']}`。知识图谱待确认项 **P-01**（寄存器精确地址）的复核清单。",
        "",
        "## 1. 结论",
        "",
        f"`data/seed.json` 的 **{s['total']}** 个演示字段与 "
        f"**{report['meta']['reference_fields']}** 行权威参考表对照结果：",
        "",
        _md_table(["状态", "数量", "含义"],
                  [["verified", s["by_status"].get("verified", 0), "名称精确匹配且页/地址一致"],
                   ["address_resolved", s["resolvable_offsets"],
                    "名称精确匹配、演示 offset 为 pending，可参考表回填"],
                   ["mismatch", s["mismatches"], "名称精确匹配但页/地址不一致，需修正"],
                   ["candidate", s["by_status"].get("candidate", 0),
                    "别名或地址推断，需人工对照 OIF 原文"],
                   ["unresolved", s["by_status"].get("unresolved", 0),
                    "未匹配，多为演示合成字段"]]),
        "",
        f"其中 {s['addressable_demo_fields']} 个字段已有可解析地址、"
        f"{s['pending_offsets']} 个仍为 `pending`/占位；"
        f"**{s['resolvable_offsets']} 个精确名称字段可直接给出权威 byte**，"
        f"另有 **{s['high_confidence_pending_candidates']} 个高置信度别名候选**可供 P-01 复核。"
        f"候选置信度分布：{s['candidate_confidence']}（`low` 一律视为未解决）。",
        "",
        "> ⚠️ 本报告只做只读对照，**不修改 `seed.json`**，也不参与任何硬件写入。"
        "字段名与地址属 OIF 版权事实标识，许可边界见 `NOTICE` 第 5–8 节；"
        "最终以 OIF 规范原文为准。",
        "",
        "## 2. 可直接回填的地址（P-01 优先项）",
        "",
        _md_table(["演示字段", "demo 页", "demo offset", "参考页", "参考 byte",
                   "权威 key_id", "表号", "PDF 页"], [row(r) for r in resolved]),
        "## 3. 已验证字段",
        "",
        _md_table(["演示字段", "demo 页", "demo offset", "参考页", "参考 byte",
                   "权威 key_id", "表号", "PDF 页"], [row(r) for r in verified]),
        "## 4. 地址 / 页不一致（需修正）",
        "",
        _md_table(["演示字段", "demo 页", "demo offset", "参考页", "参考 byte",
                   "权威 key_id", "表号", "PDF 页"], [row(r) for r in mismatch]),
        ("" if not mismatch else
         "\n".join(f"- `{r['field_key']}`: " + "; ".join(r["notes"]) for r in mismatch) + "\n"),
        "## 5. 高置信度可回填候选（P-01 次优先项）",
        "",
        "> 名称高度相似且同页，但演示 offset 为 `pending`；仍需对照 OIF 原文确认后使用。",
        "",
        _md_table(["演示字段", "demo 页", "demo offset", "参考页", "参考 byte",
                   "权威 key_id", "表号", "PDF 页", "置信度", "相似度"],
                  [confidence_row(r) for r in high_pending]),
        "## 6. 别名 / 地址推断候选（需人工确认）",
        "",
        "> `low` 置信度多为「地址碰巧相同、名称无关」，不要当作字段别名。",
        "",
        _md_table(["演示字段", "demo 页", "demo offset", "参考页", "参考 byte",
                   "权威 key_id", "表号", "PDF 页", "置信度", "相似度"],
                  [confidence_row(r) for r in candidates[:40]]),
        (f"_仅列前 40 条，共 {len(candidates)} 条，完整清单见 JSON。_\n"
         if len(candidates) > 40 else ""),
        "## 7. 未匹配字段（演示合成）",
        "",
        ", ".join(f"`{r['field_key']}`" for r in unresolved) or "_（无）_",
        "",
        "## 8. 复现与边界",
        "",
        "```bash",
        "python tools/import_cmis53.py          # 重建权威参考数据",
        "python tools/verify_seed_fields.py     # 生成本报告",
        "python tools/verify_seed_fields.py --strict   # CI：存在地址不一致时返回 1",
        "python tools/test_seed_verification.py        # 回归测试",
        "```",
        "",
        "- 匹配顺序：精确字段名 → 精确 `(page, byte)` 地址 → 模糊字段名"
        "（`difflib`，阈值 0.62）。模糊结果一律标记为 `candidate`。",
        "- 演示模型的 `field_key` 多为自造别名（如 `ModuleIdentifier` 对应"
        " `SFF8024Identifier`），`data_type` 也是展示用途的粗粒度类型，"
        "因此类型/access 差异只记录、不判定失败。",
        "- `Lower/11h`、`A0h-AFh` 等复合页标签会展开；`pending`、`banked`、"
        "`Staged Control Set` 等占位不计为可解析地址。",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- entry point

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 when any exact-name field has a page/byte mismatch")
    args = parser.parse_args()

    def resolve(path: Path) -> Path:
        return (path if path.is_absolute() else ROOT / path).resolve()

    seed_path, ref_path = resolve(args.seed), resolve(args.reference)
    for path in (seed_path, ref_path):
        if not path.is_file():
            print(f"ERROR: input file not found: {path}", file=sys.stderr)
            return 2

    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    reference = json.loads(ref_path.read_text(encoding="utf-8"))
    report = build_report(seed, reference)

    out_json, out_md = resolve(args.out_json), resolve(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    out_md.write_bytes(render_markdown(report).encode("utf-8"))

    s = report["summary"]
    print(f"Wrote {out_json} ({out_json.stat().st_size:,} bytes)")
    print(f"Wrote {out_md} ({out_md.stat().st_size:,} bytes)")
    print(f"  seed={s['total']} reference={report['meta']['reference_fields']} "
          f"status={s['by_status']}")
    print(f"  resolvable_offsets={s['resolvable_offsets']} mismatches={s['mismatches']} "
          f"pending_offsets={s['pending_offsets']}")
    if args.strict and s["mismatches"]:
        print("STRICT: mismatches present", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
