"""devctl command line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import cloudbuild, hooks, initcmd, integrity, procs, report, unity, verify, versions
from .config import PROFILES, load_config, reports_directory
from .errors import EXIT_EXECUTION, DevctlError


def _add_global(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=argparse.SUPPRESS, help="repository root (default: cwd)")
    parser.add_argument("--reports", default=argparse.SUPPRESS, help="reports directory")
    parser.add_argument("--config", default=argparse.SUPPRESS, help="config file path")
    parser.add_argument("--platform-home", default=argparse.SUPPRESS, help="dev-platform checkout")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    _add_global(common)
    parser = argparse.ArgumentParser(
        prog="devctl",
        description="Single verification command shared by local development and CI",
    )
    _add_global(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", parents=[common], help="render a repository template")
    init_parser.add_argument("--template", required=True, choices=sorted(initcmd.TEMPLATE_PROFILES))
    init_parser.add_argument("--name", required=True)
    init_parser.add_argument("--dest", required=True)
    init_parser.add_argument("--owner", default="ghdtmdwns133")
    init_parser.add_argument("--ref", default="v1")
    init_parser.add_argument("--min-coverage", type=int, default=None)
    init_parser.add_argument("--enable-codecov", action="store_true")
    init_parser.add_argument("--private", action="store_true")
    init_parser.add_argument("--force", action="store_true")

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

    hooks_parser = sub.add_parser("hooks", parents=[common], help="git hook management")
    hooks_sub = hooks_parser.add_subparsers(dest="hooks_command", required=True)
    install_parser = hooks_sub.add_parser("install", parents=[common])
    install_parser.add_argument("--force", action="store_true")
    hooks_sub.add_parser("pre-commit", parents=[common])

    versions_parser = sub.add_parser(
        "versions", parents=[common], help="toolchain version contract"
    )
    versions_parser.add_argument("--check", action="store_true")
    versions_parser.add_argument("--profile", choices=list(PROFILES), default=None)

    sub.add_parser("summary", parents=[common], help="print generated summaries")
    return parser


def _root(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd()).resolve()


def _platform_home(args: argparse.Namespace) -> Path:
    value = getattr(args, "platform_home", None) or os.environ.get("DEVPLATFORM_HOME")
    home = Path(value).expanduser().resolve() if value else Path(__file__).resolve().parents[3]
    if not home.is_dir():
        raise DevctlError(2, f"platform home not found: {home}")
    return home


def _config(args: argparse.Namespace, root: Path, profile: str | None = None):
    return load_config(root, getattr(args, "config", None), profile)


def _reports(args: argparse.Namespace, root: Path, config) -> Path:
    return reports_directory(root, config, getattr(args, "reports", None))


def _profile_for_unity(args: argparse.Namespace, config) -> str:
    return getattr(args, "profile", None) or config.profile or "unity"


def _dispatch(args: argparse.Namespace) -> int:
    root = _root(args)
    if args.command == "init":
        platform_home = _platform_home(args)
        initcmd.init(
            template=args.template,
            name=args.name,
            dest=Path(args.dest),
            platform_home=platform_home,
            owner=args.owner,
            ref=args.ref,
            min_coverage=args.min_coverage,
            enable_codecov=args.enable_codecov,
            private=args.private,
            force=args.force,
        )
        return 0

    if args.command == "verify":
        config = _config(args, root, args.profile)
        minimum = args.min_coverage if args.min_coverage is not None else config.coverage_minimum
        return verify.run_verify(
            args.profile,
            root,
            _reports(args, root, config),
            config,
            _platform_home(args),
            minimum,
            unity_build=args.unity_build,
            upload_coverage=args.upload_coverage,
            fail_fast=args.fail_fast,
        )

    if args.command == "unity":
        config = _config(args, root)
        reports = _reports(args, root, config)
        profile = _profile_for_unity(args, config)
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
            result = unity.coverage_upload(root, reports, _platform_home(args), profile=profile)
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

    if args.command == "hooks":
        if args.hooks_command == "install":
            hooks.install_hooks(root, _platform_home(args), force=args.force)
            return 0
        config = _config(args, root)
        return hooks.pre_commit(root, config, _reports(args, root, config))

    if args.command == "versions":
        config = _config(args, root, args.profile)
        profile = args.profile or config.profile
        checks = versions.check_versions(config, profile, root, _platform_home(args))
        if args.check:
            return versions.report_checks(checks)
        return versions.print_table(checks)

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
