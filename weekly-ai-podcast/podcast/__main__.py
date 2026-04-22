from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import audio, config, email_sender, github_pr, research, script


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def cmd_research(args: argparse.Namespace) -> int:
    when = _parse_date(args.date) or config.episode_date()
    out = config.episode_dir(when)
    findings = research.research_and_validate(out, today=when)
    print(f"Wrote {out}/findings.json ({sum(len(v) for v in findings.values())} items)")
    return 0


def cmd_script(args: argparse.Namespace) -> int:
    when = _parse_date(args.date) or config.episode_date()
    out = config.episode_dir(when)
    findings = json.loads((out / "findings.json").read_text())
    sc = script.generate_script(findings, when=when)
    script.write_artifacts(sc, findings, out)
    print(f"Wrote {out}/script.md ({script.count_words(sc['turns'])} words)")
    return 0


def cmd_audio(args: argparse.Namespace) -> int:
    script_path = Path(args.script) if args.script else (config.episode_dir() / "script.json")
    out_path = Path(args.out) if args.out else (script_path.parent / "episode.mp3")
    sc = audio.load_script(script_path)
    if args.silent:
        audio.synthesize_silent_stub(sc, out_path)
    else:
        audio.synthesize_script(sc, out_path, include_intro=not args.no_intro)
    print(f"Wrote {out_path}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    when = _parse_date(args.date) or config.episode_date()
    out = config.episode_dir(when)
    out.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        fixtures = config.REPO_ROOT / "tests" / "fixtures"
        findings = json.loads((fixtures / "findings.json").read_text())
        sc = json.loads((fixtures / "mini_script.json").read_text())
        research.write_artifacts(findings, out)
        script.write_artifacts(sc, findings, out)
        audio.synthesize_silent_stub(sc, out / "episode.mp3")
    else:
        findings = research.research_and_validate(out, today=when)
        sc = script.generate_script(findings, when=when)
        script.write_artifacts(sc, findings, out)
        audio.synthesize_script(sc, out / "episode.mp3")

    if args.dry_run or args.no_pr:
        print(f"Generated locally at {out} (no PR opened)")
        return 0

    preview = "\n".join(
        f"{t['speaker'].upper()}: {t['text']}" for t in sc["turns"][:6]
    ) + "\n..."
    pr = github_pr.create_episode_pr(when=when, episode_dir=out, script_preview=preview)
    email_sender.send_reviewer_notice(
        when=when,
        pr_url=pr["url"],
        artifact_url=pr["artifact_url"],
        script_preview=preview,
    )
    print(f"Opened PR #{pr['number']} at {pr['url']}")
    return 0


def cmd_ship(args: argparse.Namespace) -> int:
    approved = github_pr.find_approved_pr()
    if not approved:
        print("No approved PR found — skipping.")
        return 0

    github_pr.checkout_branch(approved.branch)
    when = date.fromisoformat(approved.branch.split("/", 1)[1])

    download_dir = config.REPO_ROOT / ".artifact"
    mp3 = github_pr.download_artifact(approved.artifact_run_id, download_dir)

    findings = json.loads((config.episode_dir(when) / "findings.json").read_text())

    log = email_sender.send_episode(
        when=when,
        findings=findings,
        attachment_path=mp3,
    )
    shipped_path = email_sender.append_shipped_log(when, log)

    github_pr.commit_and_push_shipped_log(when, shipped_path, approved.branch)
    github_pr.merge_pr(approved.number)

    ok = sum(1 for r in log["results"] if r["status"] == "ok")
    fail = sum(1 for r in log["results"] if r["status"] != "ok")
    print(f"Shipped episode {when.isoformat()}: {ok} delivered, {fail} failed.")
    return 0 if fail == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podcast")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_research = sub.add_parser("research", help="Run web-search research + validation only")
    p_research.add_argument("--date", help="Episode date (YYYY-MM-DD); defaults to this Friday")
    p_research.set_defaults(func=cmd_research)

    p_script = sub.add_parser("script", help="Generate dialogue from existing findings.json")
    p_script.add_argument("--date", help="Episode date (YYYY-MM-DD); defaults to this Friday")
    p_script.set_defaults(func=cmd_script)

    p_audio = sub.add_parser("audio", help="Synthesize MP3 from a script.json")
    p_audio.add_argument("--script", help="Path to script.json", default=None)
    p_audio.add_argument("--out", help="Output mp3 path", default=None)
    p_audio.add_argument("--silent", action="store_true", help="Produce silent placeholder (no TTS API calls)")
    p_audio.add_argument("--no-intro", action="store_true", help="Skip intro sting")
    p_audio.set_defaults(func=cmd_audio)

    p_gen = sub.add_parser("generate", help="Full pipeline: research → script → audio → PR")
    p_gen.add_argument("--date", help="Episode date (YYYY-MM-DD); defaults to this Friday")
    p_gen.add_argument("--dry-run", action="store_true", help="Use fixture findings, silent audio, no PR")
    p_gen.add_argument("--no-pr", action="store_true", help="Skip PR creation (local only)")
    p_gen.set_defaults(func=cmd_generate)

    p_ship = sub.add_parser("ship", help="Find approved PR, download artifact, send email, merge")
    p_ship.set_defaults(func=cmd_ship)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
