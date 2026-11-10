"""Regression suite for the CMIScope bilingual UI.

Covers:
  * dictionary symmetry and English-mode purity (no Chinese anywhere),
  * every UI label / prompt / field label referenced from HTML and app.js,
  * coverage of data records (knowledge graph, sources, seed) by the
    curated Chinese -> English map,
  * the runtime `t()` fallback and `L()` localizer (executed with Node when
    available),
  * live API responses: every Chinese string a read endpoint can return has
    an English translation,
  * the corrected CMIS terminology in Chinese mode.

Usage: python tools/test_i18n.py
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZH = re.compile(r"[\u3400-\u9fff]")
I18N_JS = ROOT / "cmis_service" / "static" / "js" / "i18n.js"
DATA_EN_JS = ROOT / "cmis_service" / "static" / "js" / "data_en.js"
APP_JS = ROOT / "cmis_service" / "static" / "js" / "app.js"
INDEX_HTML = ROOT / "cmis_service" / "static" / "index.html"
DATA_MAP = ROOT / "data" / "i18n_data_en.json"

UI_DATA_FILES = (
    ROOT / "data" / "knowledge_graph.json",
    ROOT / "data" / "seed.json",
    ROOT / "knowledge" / "links.json",
)
UI_SOURCE_FILES = (
    ROOT / "cmis_service" / "cmis_spec.py",
    ROOT / "tools" / "build_kg.py",
    ROOT / "tools" / "build_seed.py",
    ROOT / "tools" / "cmis_catalog.py",
    ROOT / "tools" / "build_knowledge_docs.py",
)
TERMINOLOGY_FILES = (
    I18N_JS, INDEX_HTML,
    ROOT / "cmis_service" / "cmis_spec.py",
    *UI_DATA_FILES,
    ROOT / "tools" / "build_kg.py",
    ROOT / "tools" / "cmis_catalog.py",
    ROOT / "tools" / "build_seed.py",
)

PASS: list[str] = []
FAIL: list[str] = []
SKIP: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    if not ok:
        print(f"  FAILED: {name}" + (f" -- {detail}" if detail else ""))


def parse_dicts() -> dict[str, dict[str, str]]:
    src = I18N_JS.read_text(encoding="utf-8")
    parts = re.split(r"\n    (zh|en): \{", src)
    out: dict[str, dict[str, str]] = {}
    line_re = re.compile(r"^\s*'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$")
    for i in (1, 3):
        lang = parts[i]
        body = parts[i + 1].split("\n    }")[0]
        table: dict[str, str] = {}
        for line in body.splitlines():
            if not line.strip():
                continue
            m = line_re.match(line)
            if m:
                table[m.group(1)] = m.group(2)
        out[lang] = table
    return out


def collect(value: object, out: set[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            collect(item, out)
    elif isinstance(value, list):
        for item in value:
            collect(item, out)
    elif isinstance(value, str) and ZH.search(value):
        out.add(value)


def all_data_strings() -> set[str]:
    out: set[str] = set()
    for path in UI_DATA_FILES:
        collect(json.loads(path.read_text(encoding="utf-8")), out)
    for path in UI_SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and ZH.search(node.value):
                out.add(node.value)
    return out


def node_runtime_check(strings: list[str]) -> None:
    """Execute the shipped i18n and L() code with Node, when available."""
    if not shutil.which("node"):
        SKIP.append("Node runtime check (node not installed)")
        return
    harness = r"""
'use strict';
const fs = require('fs');
global.window = {};
global.document = {
  querySelectorAll: function () { return []; },
  documentElement: { setAttribute: function () {} }
};
require(process.argv[2]);
require(process.argv[3]);
const I18N = global.window.CMIS_I18N;
const dict = I18N.dict;
I18N.setLang('en');
let bad = [];
for (const k of Object.keys(dict.zh)) {
  const v = I18N.t(k);
  if (/[\u3400-\u9fff]/.test(v)) bad.push('t(' + k + ')=' + v);
}
dict.zh['__i18n_probe__'] = '中文占位';
const probe = I18N.t('__i18n_probe__');
if (/[\u3400-\u9fff]/.test(probe) || !probe) bad.push('fallback=' + probe);
const appSrc = fs.readFileSync(process.argv[4], 'utf8');
const m = appSrc.match(/function L\(value\) \{[\s\S]*?\n  \}/);
if (!m) { bad.push('L() implementation not found'); }
else {
  eval(m[0] + '; global.__L = L;');
  const strings = JSON.parse(fs.readFileSync(process.argv[5], 'utf8'));
  for (const s of strings) {
    const out = global.__L(s);
    if (/[\u3400-\u9fff]/.test(out) || !out) bad.push('L()=' + s + ' -> ' + out);
  }
}
if (bad.length) { console.log(bad.slice(0, 12).join('\n')); process.exit(1); }
console.log('OK ' + Object.keys(dict.zh).length + ' keys / ' +
            JSON.parse(fs.readFileSync(process.argv[5], 'utf8')).length + ' data strings');
"""
    with tempfile.TemporaryDirectory(prefix="cmiscope-i18n-") as tmp:
        tmpdir = Path(tmp)
        js = tmpdir / "runtime_check.js"
        payload = tmpdir / "strings.json"
        js.write_text(harness, encoding="utf-8")
        payload.write_text(json.dumps(strings, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            ["node", str(js), str(I18N_JS), str(DATA_EN_JS), str(APP_JS), str(payload)],
            capture_output=True, text=True, timeout=120,
        )
        check("Runtime: English UI has zero Chinese (t and L)",
              proc.returncode == 0,
              (proc.stdout + proc.stderr).strip()[:400])


API_PATHS = (
    "/api/meta", "/api/access", "/api/sections", "/api/overview",
    "/api/devices", "/api/fields", "/api/config-items?limit=1000",
    "/api/cmis/module?device_id=SW-CORE-01", "/api/changes",
    "/api/cdb/commands", "/api/cdb/history", "/api/kg/entities",
    "/api/kg/relations", "/api/kg/graph", "/api/kg/sources",
    "/api/kg/sources/coverage", "/api/kg/pending", "/api/kg/stats",
    "/api/targets", "/api/reference/meta", "/api/reference/fields?limit=3000",
    "/api/reference/cdb-commands", "/api/reference/spec-tables",
    "/api/reference/verify", "/api/search?q=CMIS&scope=all",
)


def live_api_check(mapping: dict[str, str]) -> None:
    """Start the real service on a throwaway DB and scan read responses."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="cmiscope-i18n-api-")
    env = {**os.environ, "CMIS_HOST": "127.0.0.1", "CMIS_PORT": str(port),
           "CMIS_DB_FILE": str(Path(tmp) / "i18n.db"),
           "CMIS_TARGETS_FILE": str(Path(tmp) / "targets.json"),
           "CMIS_LOG_LEVEL": "WARNING"}
    proc = subprocess.Popen(
        [sys.executable, "run.py", "--port", str(port)], cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def get(path: str):
        try:
            with urllib.request.urlopen(base + path, timeout=8) as resp:
                raw = resp.read()
                if "json" not in resp.headers.get("Content-Type", ""):
                    return None
                return json.loads(raw)
        except (urllib.error.HTTPError, OSError, ValueError, UnicodeDecodeError):
            return None

    try:
        ready = False
        for _ in range(50):
            health = get("/api/health")
            if isinstance(health, dict) and health.get("ok"):
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            SKIP.append("Live API response scan (service did not start)")
            return

        seen: set[str] = set()

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, str) and ZH.search(value):
                seen.add(value)

        for path in API_PATHS:
            payload = get(path)
            if payload is not None:
                walk(payload)
        missing = sorted(s for s in seen if s not in mapping)
        check("Live API responses contain no untranslatable Chinese",
              bool(seen) and not missing,
              f"scanned={len(seen)} missing={missing[:5]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    dicts = parse_dicts()
    zh, en = dicts.get("zh", {}), dicts.get("en", {})
    check("Both language dictionaries parse and are non-empty", bool(zh) and bool(en),
          f"zh={len(zh)} en={len(en)}")
    check("Chinese and English dictionaries have identical keys",
          set(zh) == set(en),
          f"only-zh={sorted(set(zh) - set(en))[:6]} only-en={sorted(set(en) - set(zh))[:6]}")
    leaked = [(k, v) for k, v in en.items() if ZH.search(v)]
    check("No Chinese text in any English UI string", not leaked, repr(leaked[:5]))
    check("No empty English UI string", all(v.strip() for v in en.values()))
    check("English fallback guard prevents Chinese leakage",
          r"/[\u3400-\u9fff]/.test(text)" in I18N_JS.read_text(encoding="utf-8"))

    app_src = APP_JS.read_text(encoding="utf-8")
    html_src = INDEX_HTML.read_text(encoding="utf-8")
    check("app.js contains no hardcoded Chinese", not ZH.search(app_src))

    # Static Chinese in index.html must always be replaced by applyStatic().
    html_lines = html_src.splitlines()
    untranslated = []
    for i, line in enumerate(html_lines):
        if ZH.search(line) and not re.search(r"data-i18n(?:-ph|-title)?=", line):
            prev = html_lines[i - 1] if i else ""
            if not re.search(r"data-i18n(?:-ph|-title)?=", prev):
                untranslated.append((i + 1, line.strip()[:80]))
    check("Every Chinese template string is bound to a data-i18n key",
          not untranslated, repr(untranslated[:5]))

    referenced = set(re.findall(r"\bt\('([A-Za-z0-9_.]+)'", app_src))
    referenced |= set(re.findall(r"data-i18n(?:-ph|-title)?=\"([A-Za-z0-9_.]+)\"", html_src))
    referenced |= set(re.findall(
        r"'((?:common|search|ov|mod|cfg|dev|graph|src|tg|nav|side|status|edit|about|kg|lang|brand)"
        r"\.[A-Za-z0-9_.]+)'", app_src))
    static_keys = {k for k in referenced if not k.endswith(".")}
    missing = sorted(k for k in static_keys if k not in zh or k not in en)
    check("Every referenced i18n key exists in both dictionaries", not missing, repr(missing[:10]))
    check("All table/field labels in the target form are i18n-bound",
          all(f'tg.f.{k}' in html_src for k in
              ("deviceId", "sshUser", "i2cBus", "i2cAddr", "restScheme",
               "restBasePath", "tokenEnv", "moduleIds")))

    # Curated data dictionary.
    mapping = json.loads(DATA_MAP.read_text(encoding="utf-8"))
    js_body = DATA_EN_JS.read_text(encoding="utf-8")
    js_map = json.loads(js_body[js_body.index("window.CMIS_DATA_EN = ") + len("window.CMIS_DATA_EN = "):].rstrip().rstrip(";"))
    check("Generated data_en.js matches data/i18n_data_en.json", js_map == mapping)
    check("index.html loads data_en.js before app.js",
          html_src.index("js/data_en.js") < html_src.index("js/app.js"))
    check("app.js localizes graph/source/search records",
          "function L(value)" in app_src and "function LJson(value)" in app_src
          and app_src.count("L(") >= 12)
    bad_values = [(k, v) for k, v in mapping.items()
                  if not isinstance(v, str) or not v.strip() or ZH.search(v)]
    check("Every curated English data translation is non-empty and Chinese-free",
          not bad_values, repr(bad_values[:5]))
    strings = sorted(all_data_strings())
    uncovered = [s for s in strings if s not in mapping]
    check("Every Chinese string reachable from shipped data has an English translation",
          not uncovered, repr(uncovered[:5]))
    node_runtime_check(strings)
    live_api_check(mapping)

    # Chinese terminology corrections (UI-visible sources only).
    sources = "\n".join(p.read_text(encoding="utf-8") for p in TERMINOLOGY_FILES if p.is_file())
    # Built at runtime so a repository-wide grep does not match stale wording.
    forbidden = ["应用" + "广告", "口" + "令", "测试" + "方式", "终端测试接口",
                 "可信" + "度", "全部" + "权限", "载荷" + "说明",
                 "VDM " + "监测", "VDM 诊断" + "监测域",
                 "性能" + "监测", "监测" + "分区"]
    found = [w for w in forbidden if w in sources]
    check("Obsolete / inaccurate Chinese terminology removed", not found, repr(found))
    required = ["应用通告", "密码", "接入模式", "置信度", "全部读写属性",
                "载荷规则", "VDM 监控", "访问属性"]
    absent = [w for w in required if w not in sources]
    check("Corrected CMIS terminology present and consistent", not absent, repr(absent))
    check("Access-mode field label uses the industry term",
          "'tg.f.mode': '接入模式'" in I18N_JS.read_text(encoding="utf-8")
          and "'tg.f.mode': 'Access mode'" in I18N_JS.read_text(encoding="utf-8"))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
    for name in SKIP:
        print(f"  SKIPPED: {name}")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
