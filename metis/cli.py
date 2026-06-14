import argparse
import json

from . import __version__


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="metis",
        description="Metis: quality x hardware x dollars for local LLMs.")
    p.add_argument("--version", action="version", version=f"metis {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fingerprint", help="show this machine's hardware identity")

    sp = sub.add_parser("suite", help="list the task suite")
    sp.add_argument("--suite", default="v1")

    rp = sub.add_parser("run", help="collect a benchmark run")
    rp.add_argument("--models", required=True,
                    help="comma-separated model names, e.g. qwen3:1.7b,qwen3:8b")
    rp.add_argument("--backend", default="ollama",
                    choices=["ollama", "mock", "cloud", "llamacpp"])
    rp.add_argument("--repeats", type=int, default=3)
    rp.add_argument("--suite", default="v1")
    rp.add_argument("--include", default=None,
                    help="comma-separated task-id substrings to filter")
    rp.add_argument("--temperature", type=float, default=0.0)
    rp.add_argument("--seed", type=int, default=1234)
    rp.add_argument("--num-ctx", type=int, default=4096)
    rp.add_argument("--num-gpu", type=int, default=None,
                    help="GPU layers to offload (Ollama decides if unset)")
    rp.add_argument("--keep-alive", default="15m")
    rp.add_argument("--think", choices=["on", "off"], default=None,
                    help="force thinking on/off for reasoning models")
    rp.add_argument("--timeout", type=int, default=600,
                    help="per-generation timeout, seconds")
    rp.add_argument("--cloud-provider", choices=["openai", "anthropic"],
                    default=None,
                    help="cloud backend provider (default: openai)")
    rp.add_argument("--cloud-base-url", default=None,
                    help="cloud backend API base URL")
    rp.add_argument("--cloud-api-key-env", default=None,
                    help="environment variable containing the cloud API key")
    rp.add_argument("--cloud-api-version", default=None,
                    help="provider API version, when required")
    rp.add_argument("--llamacpp-base-url", default="http://localhost:8080",
                    help="llama-server base URL (llamacpp backend)")
    rp.add_argument("--llamacpp-gpu-layers", type=int, default=None,
                    help="n_gpu_layers the llama-server was launched with "
                         "(recorded into run metadata, not enforced)")
    rp.add_argument("--out", default="results")
    rp.add_argument("--force", action="store_true",
                    help="skip the preflight quiesce check (recorded)")

    scp = sub.add_parser("score", help="score a collected run")
    scp.add_argument("run_dir")
    scp.add_argument("--no-code-exec", action="store_true",
                     help="skip scorers that execute model-generated code")

    jp = sub.add_parser("judge", help="run tier-2 judge scoring")
    jp.add_argument("run_dir")
    jp.add_argument("--config", default="config/judge.yaml")

    rep = sub.add_parser("report", help="generate markdown + HTML reports")
    rep.add_argument("run_dir")

    ec = sub.add_parser("economics", help="break-even analysis for a run")
    ec.add_argument("run_dir")
    ec.add_argument("--pricing", default="config/pricing.yaml")

    sat = sub.add_parser("saturation",
                         help="ceiling-effect metrics for a scored run")
    sat.add_argument("run_dir")
    sat.add_argument("--out", default=None,
                     help="markdown output path (default: <run_dir>/saturation.md)")

    args = p.parse_args(argv)

    if args.cmd == "fingerprint":
        from . import fingerprint
        print(json.dumps(fingerprint.collect(), indent=2))

    elif args.cmd == "suite":
        from .suite.loader import load_suite
        suite = load_suite(args.suite)
        print(f"suite v{suite['version']} — {len(suite['tasks'])} tasks")
        for t in suite["tasks"]:
            print(f"  {t['id']:<35} {t['category']:<22} "
                  f"{t['scoring']['type']}")

    elif args.cmd == "run":
        from .runner import run
        options = {
            "temperature": args.temperature,
            "seed": args.seed,
            "num_ctx": args.num_ctx,
            "num_gpu": args.num_gpu,
            "keep_alive": args.keep_alive,
            "think": {"on": True, "off": False}.get(args.think),
        }
        backend_kwargs = None
        if args.backend == "ollama":
            backend_kwargs = {"timeout_s": args.timeout}
        elif args.backend == "cloud":
            backend_kwargs = {
                "provider": args.cloud_provider or "openai",
                "base_url": args.cloud_base_url,
                "api_key_env": args.cloud_api_key_env,
                "api_version": args.cloud_api_version,
                "timeout_s": args.timeout,
            }
        elif args.backend == "llamacpp":
            backend_kwargs = {
                "base_url": args.llamacpp_base_url,
                "n_gpu_layers": args.llamacpp_gpu_layers,
                "timeout_s": args.timeout,
            }
        run(models=[m.strip() for m in args.models.split(",") if m.strip()],
            backend_name=args.backend,
            repeats=args.repeats,
            suite_dir=args.suite,
            include=[s.strip() for s in args.include.split(",")] if args.include else None,
            options=options,
            out_root=args.out,
            force=args.force,
            backend_kwargs=backend_kwargs)

    elif args.cmd == "score":
        from .scoring.score_run import score_run
        summary = score_run(args.run_dir,
                            allow_code_exec=not args.no_code_exec)
        print(json.dumps(summary, indent=2))

    elif args.cmd == "judge":
        from .scoring.judge import judge_run
        summary = judge_run(args.run_dir, args.config)
        print(json.dumps(summary, indent=2))

    elif args.cmd == "report":
        from .report import write_reports
        md, html = write_reports(args.run_dir)
        print(f"wrote {md}\nwrote {html}")

    elif args.cmd == "economics":
        from .economics import compute
        print(compute(args.run_dir, args.pricing))

    elif args.cmd == "saturation":
        from .saturation import compute as sat_compute, render_markdown, write_report
        out = write_report(args.run_dir, args.out)
        print(render_markdown(sat_compute(args.run_dir)))
        print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
