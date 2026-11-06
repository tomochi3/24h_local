"""集めた投稿を Codex CLI / Claude Code CLI で日本語要約する。

ai_edit_TT と同じく月額プランのログインだけを使う。APIキーの環境変数は子プロセスに渡さない。
失敗しても要約なしでPDFは作る。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .xapi import Post

TIMEOUT = 600
_API_KEY_ENV = ("OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["overview", "topics", "accounts"],
    "properties": {
        "overview": {"type": "string"},
        "topics": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "summary", "post_ids"],
            "properties": {"title": {"type": "string"}, "summary": {"type": "string"},
                           "post_ids": {"type": "array", "items": {"type": "string"}}}}},
        "accounts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["username", "summary"],
            "properties": {"username": {"type": "string"}, "summary": {"type": "string"}}}},
    },
}

PROMPT = """あなたは技術系ニュースの編集者です。以下はXの複数アカウントの最近の投稿（JSON）です。
忙しい読者が朝に数分で把握できるよう、日本語でまとめてください。

- overview: 全体で今日いちばん大事なことを3〜5文で。
- topics: 内容ごとにまとめた話題（3〜8個）。title は短い見出し、summary は2〜4文。
  論文・ツール・リリース名などの固有名詞は残す。post_ids には根拠になった投稿の id を入れる。
- accounts: アカウントごとに、その人が何について発信していたかを1〜3文で（投稿があったアカウントのみ）。

投稿に書かれていないことは推測で足さないでください。出力は指定のJSONだけにしてください。

投稿:
"""


class SummaryError(RuntimeError):
    pass


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _API_KEY_ENV}


def build_prompt(posts: list[Post]) -> str:
    items = [p.to_dict() for p in posts]
    return PROMPT + json.dumps(items, ensure_ascii=False, indent=1)


def validate(obj) -> dict:
    if not isinstance(obj, dict) or not isinstance(obj.get("overview"), str):
        raise SummaryError("要約の形式が不正です")
    topics = [t for t in obj.get("topics") or [] if isinstance(t, dict) and t.get("title")]
    accounts = [a for a in obj.get("accounts") or [] if isinstance(a, dict) and a.get("username")]
    return {"overview": obj["overview"], "topics": topics, "accounts": accounts}


def summarize_codex(prompt: str, model: str = "") -> dict:
    with tempfile.TemporaryDirectory(prefix="xdigest_codex_") as tmp:
        schema, output = Path(tmp) / "schema.json", Path(tmp) / "result.json"
        schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
        cmd = ["codex", "exec", "--sandbox", "read-only", "-c", 'approval_policy="never"',
               "--skip-git-repo-check", "--output-schema", str(schema), "-o", str(output)]
        if model:
            cmd += ["-m", model]
        cmd += ["-"]
        proc = subprocess.run(cmd, input=prompt, env=_child_env(), cwd=tmp, capture_output=True,
                              text=True, timeout=TIMEOUT)
        if proc.returncode:
            raise SummaryError(f"codex が失敗しました: {(proc.stderr or proc.stdout)[-300:]}")
        try:
            return validate(json.loads(output.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            raise SummaryError(f"codex の出力を読めません: {e}") from None


def summarize_claude(prompt: str, model: str = "sonnet") -> dict:
    with tempfile.TemporaryDirectory(prefix="xdigest_claude_") as tmp:
        cmd = ["claude", "-p", "--strict-mcp-config", "--no-session-persistence",
               "--output-format", "json", "--json-schema", json.dumps(SCHEMA), "--model", model]
        proc = subprocess.run(cmd, input=prompt, env=_child_env(), cwd=tmp, capture_output=True,
                              text=True, timeout=TIMEOUT)
        try:
            out = json.loads(proc.stdout)
        except ValueError:
            out = None
        if proc.returncode or not isinstance(out, dict) or out.get("is_error"):
            raise SummaryError(f"claude が失敗しました: {(proc.stderr or proc.stdout)[-300:]}")
        result = out.get("structured_output")
        if result is None and isinstance(out.get("result"), str):
            try:
                result = json.loads(out["result"])
            except ValueError:
                pass
        return validate(result)


def summarize(posts: list[Post], provider: str, *, claude_model: str = "sonnet",
              codex_model: str = "", log=print) -> dict | None:
    if provider == "none" or not posts:
        return None
    prompt = build_prompt(posts)
    order = ["codex", "claude"] if provider == "auto" else [provider]
    for name in order:
        try:
            if name == "codex":
                return summarize_codex(prompt, codex_model)
            return summarize_claude(prompt, claude_model)
        except FileNotFoundError:
            log(f"{name} コマンドが見つかりません")
        except (SummaryError, subprocess.TimeoutExpired) as e:
            log(f"{name} で要約できませんでした: {e}")
    return None
