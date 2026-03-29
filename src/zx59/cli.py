"""CLI entry point for 0x59."""

from __future__ import annotations

import argparse
import os
import platform
import sys
from pathlib import Path

from zx59.coordinator import ClaudeRunner, Coordinator, TurnInfo
from zx59.db import DB
from zx59.export import export_artifact, validate_export_name
from zx59.notify import notify
from zx59.runner import SubprocessClaudeRunner

_DEFAULT_PROPOSER_PROMPT = (
    "You are a thoughtful technical contributor. Propose solutions, "
    "consider trade-offs, and be willing to reach consensus."
)
_DEFAULT_CHALLENGER_PROMPT = (
    "You are a critical reviewer. Stress-test proposals, identify risks, "
    "and push for clarity. Agree only when genuinely convinced."
)


def _default_db_path() -> Path:
    if platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "0x59"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        base = Path(xdg) / "0x59"
    return base / "channels.db"


def _create_runner() -> ClaudeRunner:
    """Create the real ClaudeRunner. Monkeypatched in tests."""
    return SubprocessClaudeRunner()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="0x59", description="Inter-agent communication")
    parser.add_argument("--db", type=Path, default=None, help="Database path override")

    sub = parser.add_subparsers(dest="command")

    # chat
    chat_p = sub.add_parser("chat", help="Quick 2-agent chat")
    chat_p.add_argument("topic", help="Discussion topic")
    chat_p.add_argument("--model", default="sonnet", help="Model to use (default: sonnet)")
    chat_p.add_argument("--max-turns", type=int, default=20, help="Max turns (default: 20)")

    # discuss
    disc_p = sub.add_parser("discuss", help="Formal discussion with roles")
    disc_p.add_argument("topic", help="Discussion topic")
    disc_p.add_argument(
        "--agent", nargs=2, action="append", metavar=("ID", "PROMPT"), help="Agent id and prompt"
    )
    disc_p.add_argument("--model", default="sonnet", help="Model to use (default: sonnet)")
    disc_p.add_argument("--max-turns", type=int, default=20, help="Max turns (default: 20)")
    disc_p.add_argument("--agenda", default=None, help="Discussion agenda")

    # log
    log_p = sub.add_parser("log", help="Print full transcript")
    log_p.add_argument("channel_id", help="Channel ID")

    # decision
    dec_p = sub.add_parser("decision", help="Print decision summary")
    dec_p.add_argument("channel_id", help="Channel ID")

    # artifacts
    art_p = sub.add_parser("artifacts", help="List artifacts")
    art_p.add_argument("channel_id", help="Channel ID")

    # export
    exp_p = sub.add_parser("export", help="Export artifact to file")
    exp_p.add_argument("channel_id", help="Channel ID")
    exp_p.add_argument("file", nargs="?", default=None, help="Output file path (any path accepted)")
    exp_p.add_argument("--name", default=None, help="Artifact name to export (default: first)")

    # ls
    ls_p = sub.add_parser("ls", help="List channels")
    ls_g = ls_p.add_mutually_exclusive_group()
    ls_g.add_argument("--open", action="store_const", const="open", dest="status")
    ls_g.add_argument("--decided", action="store_const", const="decided", dest="status")
    ls_g.add_argument("--closed", action="store_const", const="closed", dest="status")

    return parser


def _print_turn(info: TurnInfo) -> None:
    """Print a turn to stdout as it happens."""
    header = f"── {info.agent_id} (turn {info.turn}/{info.max_turns}) "
    print(f"\n{header}{'─' * max(1, 60 - len(header))}")
    print(info.message, flush=True)


def _cmd_chat(args: argparse.Namespace, db: DB) -> int:
    channel_id = db.create_channel(topic=args.topic, model=args.model, max_turns=args.max_turns)
    db.add_participant(
        channel_id, "proposer", "participant", system_prompt=_DEFAULT_PROPOSER_PROMPT
    )
    db.add_participant(
        channel_id, "challenger", "participant", system_prompt=_DEFAULT_CHALLENGER_PROMPT
    )

    runner = _create_runner()
    coord = Coordinator(db, runner)
    result = coord.run(channel_id, on_turn=_print_turn)

    print(f"\n{'═' * 60}")
    print(f"Channel: {result.channel_id}")
    print(f"Status: {result.status}")
    print(f"Turns: {result.total_turns}")
    if result.decision:
        print(f"Decision: {result.decision}")
        notify("0x59 — Decision", result.decision)
    return 0


def _cmd_discuss(args: argparse.Namespace, db: DB) -> int:
    channel_id = db.create_channel(
        topic=args.topic, model=args.model, agenda=args.agenda, max_turns=args.max_turns
    )

    if args.agent:
        for agent_id, prompt in args.agent:
            db.add_participant(channel_id, agent_id, "participant", system_prompt=prompt)
    else:
        db.add_participant(
            channel_id, "proposer", "participant", system_prompt=_DEFAULT_PROPOSER_PROMPT
        )
        db.add_participant(
            channel_id, "challenger", "participant", system_prompt=_DEFAULT_CHALLENGER_PROMPT
        )

    runner = _create_runner()
    coord = Coordinator(db, runner)
    result = coord.run(channel_id, on_turn=_print_turn)

    print(f"\n{'═' * 60}")
    print(f"Channel: {result.channel_id}")
    print(f"Status: {result.status}")
    print(f"Turns: {result.total_turns}")
    if result.decision:
        print(f"Decision: {result.decision}")
        notify("0x59 — Decision", result.decision)
    return 0


def _cmd_log(args: argparse.Namespace, db: DB) -> int:
    channel = db.get_channel(args.channel_id)
    if channel is None:
        print(f"Channel {args.channel_id} not found.", file=sys.stderr)
        return 1

    print(f"Topic: {channel.topic}")
    if channel.agenda:
        print(f"Agenda: {channel.agenda}")
    print(f"Status: {channel.status}")
    print()

    for msg in db.get_messages(args.channel_id):
        print(f"[{msg.sender}] {msg.content}")
        print()
    return 0


def _cmd_decision(args: argparse.Namespace, db: DB) -> int:
    channel = db.get_channel(args.channel_id)
    if channel is None:
        print(f"Channel {args.channel_id} not found.", file=sys.stderr)
        return 1

    print(f"Topic: {channel.topic}")
    print(f"Status: {channel.status}")
    if channel.decision:
        print(f"Decision: {channel.decision}")
    else:
        print("No decision yet.")
    return 0


def _cmd_artifacts(args: argparse.Namespace, db: DB) -> int:
    artifacts = db.get_artifacts(args.channel_id)
    if not artifacts:
        print("No artifacts.")
        return 0

    for art in artifacts:
        print(f"  {art.name} ({art.content_type}, {len(art.content)} bytes)")
    return 0


def _cmd_export(args: argparse.Namespace, db: DB) -> int:
    artifacts = db.get_artifacts(args.channel_id)
    if not artifacts:
        print("No artifacts to export.", file=sys.stderr)
        return 1

    if args.name:
        matching = [a for a in artifacts if a.name == args.name]
        if not matching:
            names = ", ".join(a.name for a in artifacts)
            print(f"No artifact named '{args.name}'. Available: {names}", file=sys.stderr)
            return 1
        art = matching[0]
    else:
        art = artifacts[0]
        if len(artifacts) > 1:
            names = ", ".join(a.name for a in artifacts)
            print(f"Multiple artifacts available: {names}", file=sys.stderr)
            print(f"Exporting '{art.name}'. Use --name to select.", file=sys.stderr)

    if args.file:
        path = Path(args.file)
    else:
        try:
            path = validate_export_name(art.name)
        except ValueError as e:
            print(f"Unsafe artifact name: {e}", file=sys.stderr)
            return 1
    export_artifact(art, path)
    print(f"Exported: {path}")
    return 0


def _cmd_ls(args: argparse.Namespace, db: DB) -> int:
    channels = db.list_channels(status=getattr(args, "status", None))
    if not channels:
        print("No channels.")
        return 0

    for ch in channels:
        print(f"  {ch.id}  [{ch.status:8s}]  {ch.topic}")
    return 0


_COMMANDS = {
    "chat": _cmd_chat,
    "discuss": _cmd_discuss,
    "log": _cmd_log,
    "decision": _cmd_decision,
    "artifacts": _cmd_artifacts,
    "export": _cmd_export,
    "ls": _cmd_ls,
}


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    db_path = args.db or _default_db_path()
    db = DB(db_path)

    try:
        handler = _COMMANDS.get(args.command)
        if handler is None:
            parser.print_help()
            return 1
        return handler(args, db)
    finally:
        db.close()
