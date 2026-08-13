"""Desktop ↔ web demo voice-language parity.

Shared contract: ``scripts/demo_voice.py`` and ``web/src/utils/demoVoice.js``
normalise ids, pick a language, and resolve ``voice/<lang>/<file>`` the same
way. The shipped pack’s ``text/<lang>/`` scripts and ``<languages>`` stay
aligned with both runners.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = BTF_ROOT / "demos" / "demo_8cores"
DEMO_XML = DEMO_DIR / "demo_8cores.xml"
WEB_VOICE = BTF_ROOT / "web" / "src" / "utils" / "demoVoice.js"
WEB_XML = BTF_ROOT / "web" / "src" / "utils" / "demoXml.js"
WEB_RUNNER = BTF_ROOT / "web" / "src" / "utils" / "demoRunner.js"
WEB_APP = BTF_ROOT / "web" / "src" / "App.vue"
PY_VOICE = BTF_ROOT / "scripts" / "demo_voice.py"
PY_RUNNER = BTF_ROOT / "scripts" / "demo_runner.py"
MAKEFILE = BTF_ROOT / "Makefile"

PACK_LANGS = ("en", "zh-tw", "ja")
NORMALIZE_CASES = (
    ("en-US", "en"),
    ("zh_TW", "zh-tw"),
    ("zh-Hant", "zh-tw"),
    ("zh-HK", "zh-tw"),
    ("zh-CN", "zh"),
    ("zh-Hans", "zh"),
    ("ja-JP", "ja"),
    ("", ""),
)
PICK_CASES = (
    ("zh-TW", ["en", "zh-tw"], "en", "zh-tw"),
    ("zh-CN", ["en", "zh-tw"], "en", "zh-tw"),
    ("ja", ["en", "zh-tw"], "en", "en"),
    ("", ["en", "zh-tw"], "en", "en"),
)
CANDIDATE_CASES = (
    (
        "voice/01_title.mp3",
        "zh-TW",
        "en",
        ["voice/zh-tw/01_title.mp3", "voice/01_title.mp3", "voice/en/01_title.mp3"],
    ),
    (
        "pack/voice/zh-tw/01_title.mp3",
        "en",
        "en",
        [
            "pack/voice/en/01_title.mp3",
            "pack/voice/01_title.mp3",
            "pack/voice/zh-tw/01_title.mp3",
        ],
    ),
    ("clips/beep.wav", "zh-tw", "en", ["clips/beep.wav"]),
)


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dv = _load_mod("demo_voice", PY_VOICE)
dr = _load_mod("demo_runner", PY_RUNNER)


def _js_labels(src: str) -> dict:
    block = re.search(r"const labels = \{([\s\S]*?)\}", src)
    self_map = {}
    for key, val in re.findall(
        r"['\"]?([A-Za-z0-9-]+)['\"]?\s*:\s*['\"]([^'\"]+)['\"]",
        block.group(1) if block else "",
    ):
        self_map[key] = val
    return self_map


def _node_voice_eval() -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node not available")
    script = (
        "import { readFileSync } from 'node:fs'\n"
        "import { normalizeVoiceLang, pickVoiceLang, voicePathCandidates, mergeVoiceLangs }"
        " from './src/utils/demoVoice.js'\n"
        "import { parseDemoXml, buildVariables, parseXmlRoot } from './src/utils/demoXml.js'\n"
        "const xml = readFileSync('../demos/demo_8cores/demo_8cores.xml', 'utf8')\n"
        "const demo = parseDemoXml(xml, { xmlDir: '/pack' })\n"
        "const vars = buildVariables(parseXmlRoot(xml), { xmlDir: '/pack' })\n"
        f"const normalizeIn = {json.dumps([s for s, _ in NORMALIZE_CASES])}\n"
        f"const pickIn = {json.dumps([[p, a, f] for p, a, f, _ in PICK_CASES])}\n"
        f"const candIn = {json.dumps([[rel, lang, fb] for rel, lang, fb, _ in CANDIDATE_CASES])}\n"
        "const out = {\n"
        "  normalize: Object.fromEntries(normalizeIn.map(s => [s, normalizeVoiceLang(s)])),\n"
        "  pick: pickIn.map(([p, a, f]) => pickVoiceLang(p, a, f)),\n"
        "  candidates: candIn.map(([rel, lang, fb]) => voicePathCandidates(rel, lang, fb)),\n"
        "  languages: demo.languages,\n"
        "  varsHasLanguages: Object.prototype.hasOwnProperty.call(vars, 'languages'),\n"
        "  merge: mergeVoiceLangs(\n"
        "    { defaultId: 'en', list: [{ id: 'en', label: 'English' }] },\n"
        "    ['zh-tw', 'ja'],\n"
        "  ),\n"
        "}\n"
        "console.log(JSON.stringify(out))\n"
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".mjs", dir=BTF_ROOT / "web", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(script)
        path = fh.name
    try:
        proc = subprocess.run(
            [node, path],
            cwd=str(BTF_ROOT / "web"),
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        os.unlink(path)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout or f"node exit {proc.returncode}")
    return json.loads(proc.stdout)


class DemoVoiceSourceParityTests(unittest.TestCase):
    def test_label_maps_match(self) -> None:
        js = _js_labels(WEB_VOICE.read_text(encoding="utf-8"))
        self.assertEqual(js, dv.LABELS)
        self.assertEqual(js["zh-tw"], "中文")
        self.assertEqual(js["ja"], "日本語")

    def test_both_skip_languages_in_meta_variables(self) -> None:
        web = WEB_XML.read_text(encoding="utf-8")
        py = PY_RUNNER.read_text(encoding="utf-8")
        self.assertIn("'title', 'description', 'author', 'languages'", web)
        self.assertIn('"title", "description", "author", "languages"', py)

    def test_both_parse_languages_from_meta(self) -> None:
        web = WEB_XML.read_text(encoding="utf-8")
        py = PY_RUNNER.read_text(encoding="utf-8")
        self.assertIn("child(child(root, 'meta'), 'languages')", web)
        self.assertIn('meta.find("languages")', py)

    def test_both_runners_try_lang_then_flat_then_default(self) -> None:
        web = WEB_RUNNER.read_text(encoding="utf-8")
        py = PY_RUNNER.read_text(encoding="utf-8")
        js_voice = WEB_VOICE.read_text(encoding="utf-8")
        py_voice = PY_VOICE.read_text(encoding="utf-8")
        self.assertIn("voicePathCandidates(rel, voiceLang, voiceLangs.defaultId)", web)
        self.assertIn("voice_path_candidates(p, lang, default_lang)", py)
        self.assertIn("${prefix}/${langN}/${basename}", js_voice)
        self.assertIn("${prefix}/${basename}", js_voice)
        self.assertIn("${prefix}/${defN}/${basename}", js_voice)
        self.assertIn('add(f"{prefix}/{lang_n}/{basename}")', py_voice)
        self.assertIn('add(f"{prefix}/{basename}")', py_voice)
        self.assertIn('add(f"{prefix}/{def_n}/{basename}")', py_voice)

    def test_web_voice_menu_and_desktop_lang_flag(self) -> None:
        app = WEB_APP.read_text(encoding="utf-8")
        runner = PY_RUNNER.read_text(encoding="utf-8")
        mk = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn('class="demo-lang-select"', app)
        self.assertIn("setVoiceLang", app)
        self.assertIn("btf-demo-voice-lang", app)
        self.assertIn('"--lang"', runner)
        self.assertIn("BTFVIEWER_DEMO_LANG", runner)
        self.assertIn("XML <languages default>", runner)
        self.assertNotIn("LC_MESSAGES", runner)
        self.assertIn("DEMO_LANG", mk)
        self.assertIn("demo_voice.py status", mk)


class DemoVoiceRuntimeParityTests(unittest.TestCase):
    def test_python_matches_shared_cases(self) -> None:
        for raw, want in NORMALIZE_CASES:
            self.assertEqual(dv.normalize_voice_lang(raw), want, raw)
        for preferred, available, fallback, want in PICK_CASES:
            self.assertEqual(
                dv.pick_voice_lang(preferred, available, fallback), want, preferred
            )
        for rel, lang, fallback, want in CANDIDATE_CASES:
            got = [p.as_posix() for p in dv.voice_path_candidates(Path(rel), lang, fallback)]
            self.assertEqual(got, want, rel)

    def test_javascript_matches_python(self) -> None:
        js = _node_voice_eval()
        for raw, want in NORMALIZE_CASES:
            self.assertEqual(js["normalize"][raw], want, raw)
            self.assertEqual(js["normalize"][raw], dv.normalize_voice_lang(raw), raw)
        for i, (preferred, available, fallback, want) in enumerate(PICK_CASES):
            self.assertEqual(js["pick"][i], want, preferred)
            self.assertEqual(
                js["pick"][i],
                dv.pick_voice_lang(preferred, available, fallback),
                preferred,
            )
        for i, (rel, lang, fallback, want) in enumerate(CANDIDATE_CASES):
            self.assertEqual(js["candidates"][i], want, rel)
            py = [p.as_posix() for p in dv.voice_path_candidates(Path(rel), lang, fallback)]
            self.assertEqual(js["candidates"][i], py, rel)

        root = dr.load_demo_xml(DEMO_XML)
        py_langs = dr.parse_languages(root)
        self.assertEqual(js["languages"]["defaultId"], py_langs["defaultId"])
        self.assertEqual(js["languages"]["list"], py_langs["list"])
        self.assertFalse(js["varsHasLanguages"])
        vars_ = dr.build_variables(root, DEMO_XML, {})
        self.assertNotIn("languages", vars_)

        merged = dv.merge_voice_langs(
            {"defaultId": "en", "list": [{"id": "en", "label": "English"}]},
            ["zh-tw", "ja"],
        )
        self.assertEqual(js["merge"]["defaultId"], merged["defaultId"])
        self.assertEqual(js["merge"]["list"], merged["list"])


class DemoVoicePackParityTests(unittest.TestCase):
    def test_xml_languages_match_text_manifests(self) -> None:
        root = dr.load_demo_xml(DEMO_XML)
        langs = dr.parse_languages(root)
        self.assertEqual(langs["defaultId"], "en")
        ids = [x["id"] for x in langs["list"]]
        self.assertEqual(ids, list(PACK_LANGS))
        by_id = {x["id"]: x["label"] for x in langs["list"]}
        for lang in PACK_LANGS:
            man_path = DEMO_DIR / "text" / lang / "voice.json"
            self.assertTrue(man_path.is_file(), man_path)
            data = json.loads(man_path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], "btf-demo-voice")
            self.assertEqual(data["id"], lang)
            self.assertEqual(data["label"], by_id[lang])

    def test_translation_stems_match_english(self) -> None:
        en = sorted(p.name for p in (DEMO_DIR / "text" / "en").glob("*.txt"))
        self.assertTrue(en)
        for lang in PACK_LANGS:
            got = sorted(p.name for p in (DEMO_DIR / "text" / lang).glob("*.txt"))
            self.assertEqual(got, en, lang)
            self.assertTrue((DEMO_DIR / "text" / lang / "voice.json").is_file(), lang)

    def test_xml_audio_stems_match_english_scripts(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        stems = [
            Path(m).stem
            for m in re.findall(r'voice/([A-Za-z0-9_.-]+\.mp3)"', xml)
        ]
        scripts = sorted(p.stem for p in (DEMO_DIR / "text" / "en").glob("*.txt"))
        self.assertEqual(sorted(stems), scripts)

    def test_step1_says_web_in_every_language(self) -> None:
        en = (DEMO_DIR / "text" / "en" / "01_title.txt").read_text(encoding="utf-8")
        zh = (DEMO_DIR / "text" / "zh-tw" / "01_title.txt").read_text(encoding="utf-8")
        ja = (DEMO_DIR / "text" / "ja" / "01_title.txt").read_text(encoding="utf-8")
        self.assertIn("web app", en.lower())
        self.assertNotIn("use the desktop app", en.lower())
        self.assertIn("網頁版", zh)
        self.assertNotIn("今天我們使用桌面版", zh)
        self.assertIn("ウェブ版", ja)
        self.assertNotIn("今日はデスクトップ版", ja)

    def test_zh_tw_and_ja_scripts_avoid_latin_words(self) -> None:
        """TTS mixes badly on Latin inside CJK; keep scripts in one script."""
        latin = re.compile(r"[A-Za-z]{2,}")
        for lang in ("zh-tw", "ja"):
            for path in sorted((DEMO_DIR / "text" / lang).glob("*.txt")):
                hits = latin.findall(path.read_text(encoding="utf-8"))
                self.assertEqual(hits, [], f"{lang}/{path.name}: {hits}")


if __name__ == "__main__":
    unittest.main()
