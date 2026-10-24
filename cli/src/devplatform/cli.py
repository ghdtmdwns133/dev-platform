"""devctl command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import cloudbuild, integrity, procs, report, unity, verify
from .config import PROFILES, load_config, reports_directory
from .errors import EXIT_EXECUTION, DevctlError


def _add_global(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=argparse.SUPPRESS, help="repository root (default: cwd)")
    parser.add_argument("--reports", default=argparse.SUPPRESS, help="reports directory")
    parser.add_argument("--config", default=argparse.SUPPRESS, help="config file path")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    _add_global(common)
    parser = argparse.ArgumentParser(
        prog="devctl",
        description="Unity verification and execution commands shared by local development and CI",
    )
    _add_global(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    verify_parser = sub.add_parser("verify", parents=[common], help="run the verification gate")
    verify_parser.add_argument("--profile", required=True, choices=list(PROFILES))
    verify_parser.add_argument("--min-coverage", type=int, default=None)
    verify_parser.add_argument("--fail-fast", action="store_true")
    verify_parser.add_argument("--unity-build", action="store_true")
    verify_parser.add_argument("--upload-coverage", action="store_true")

    unity_parser = sub.add_parser("unity", parents=[common], help="Unity-specific commands")
    unity_sub = unity_parser.add_subparsers(dest="unity_command", required=True)

    integrity_parser = unity_sub.add_parser("integrity", parents=[common])
    integrity_parser.add_argument("--write-baseline", action="store_true")

    tests_parser = unity_sub.add_parser("tests", parents=[common])
    tests_parser.add_argument("--platform", choices=["EditMode", "PlayMode", "all"], default="all")

    unity_sub.add_parser("build", parents=[common])

    odin_parser = unity_sub.add_parser("odin", parents=[common])
    odin_parser.add_argument("--require-odin", action="store_true")

    junit_parser = unity_sub.add_parser("junit", parents=[common])
    junit_parser.add_argument("--in", dest="in_path", required=True)
    junit_parser.add_argument("--out", dest="out_path", required=True)

    unity_sub.add_parser("coverage-upload", parents=[common])

    cloud_parser = unity_sub.add_parser("cloud-build", parents=[common])
    cloud_parser.add_argument("--target", default=None)
    cloud_parser.add_argument("--commit", default=None)
    cloud_parser.add_argument("--timeout-min", type=int, default=None)
    cloud_parser.add_argument("--download", default=None)

    sub.add_parser("summary", parents=[common], help="print generated summaries")
    return parser


def _root(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd()).resolve()


def _config(args: argparse.Namespace, root: Path, profile: str | None = None):
    return load_config(root, getattr(args, "config", None), profile)


def _reports(args: argparse.Namespace, root: Path, config) -> Path:
    return reports_directory(root, config, getattr(args, "reports", None))


def _dispatch(args: argparse.Namespace) -> int:
    root = _root(args)
    if args.command == "verify":
        config = _config(args, root, args.profile)
        minimum = args.min_coverage if args.min_coverage is not None else config.coverage_minimum
        return verify.run_verify(
            args.profile,
            root,
            _reports(args, root, config),
            config,
            minimum,
            unity_build=args.unity_build,
            upload_coverage=args.upload_coverage,
            fail_fast=args.fail_fast,
        )

    if args.command == "unity":
        config = _config(args, root)
        reports = _reports(args, root, config)
        profile = config.profile or "unity"
        if args.unity_command == "integrity":
            result = integrity.check(root, config, write_baseline_requested=args.write_baseline)
            integrity.print_result(result)
            return 1 if result.errors else 0
        if args.unity_command == "junit":
            counts = unity.nunit_to_junit(
                Path(args.in_path) if Path(args.in_path).is_absolute() else root / args.in_path,
                Path(args.out_path) if Path(args.out_path).is_absolute() else root / args.out_path,
            )
            procs.emit_notice(
                f"JUnit XML written; {counts['tests']} tests, {counts['failures']} failures, "
                f"{counts['skipped']} skipped"
            )
            return 0
        if args.unity_command == "coverage-upload":
            result = unity.coverage_upload(root, reports, profile=profile)
            procs.emit_notice(result.detail or "coverage uploaded")
            return result.exit
        if args.unity_command == "cloud-build":
            cloudbuild.run_cloud_build(
                root,
                reports,
                config,
                target=args.target,
                commit=args.commit,
                timeout_min=args.timeout_min,
                download=args.download,
            )
            return 0
        editor = unity.require_editor(config, root)
        unity.check_editor_version(config, editor)
        if args.unity_command == "tests":
            platforms = (
                list(config.unity["testPlatforms"]) if args.platform == "all" else [args.platform]
            )
            errors: list[int] = []
            failures = False
            for platform in platforms:
                result = unity.run_tests(root, reports, config, platform, editor, profile=profile)
                procs.emit_notice(f"{result.name}: {result.status} ({result.detail})")
                if result.status == procs.STATUS_ERROR:
                    errors.append(result.exit)
                elif result.status == procs.STATUS_FAILED:
                    failures = True
            if errors:
                for code in (2, 4, 3):
                    if code in errors:
                        return code
                return EXIT_EXECUTION
            return 1 if failures else 0
        if args.unity_command == "build":
            result = unity.build_project(root, reports, config, editor, profile=profile)
            procs.emit_notice(f"{result.name}: {result.status} ({result.detail})")
            return result.exit
        if args.unity_command == "odin":
            result = unity.run_odin(
                root, reports, config, editor, profile=profile, require_odin=args.require_odin
            )
            procs.emit_notice(f"{result.name}: {result.status} ({result.detail})")
            return result.exit
        raise DevctlError(EXIT_EXECUTION, f"unknown unity command: {args.unity_command}")

    if args.command == "summary":
        config = _config(args, root)
        report.print_summaries(_reports(args, root, config))
        return 0

    raise DevctlError(EXIT_EXECUTION, f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except DevctlError as exc:
        procs.emit_error(exc.message)
        if exc.detail:
            print(exc.detail[-2000:], file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
