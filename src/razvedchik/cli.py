import argparse
from .agent import Agent
from .report import write_reports


def main() -> None:
    p = argparse.ArgumentParser(description="Разведчик — autonomous OSINT agent")
    p.add_argument("--mode", choices=["fio", "username", "nickname", "phone", "email", "photo", "combined"], required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--waves", type=int, default=4)
    p.add_argument("--per-query", type=int, default=8)
    p.add_argument("--output", default="reports")
    args = p.parse_args()
    if args.mode == "photo":
        raise SystemExit("Photo mode requires a visual-search adapter and is intentionally disabled until a legitimate image-search backend is configured.")
    inv = Agent(args.mode, args.query, args.waves, args.per_query).run()
    paths = write_reports(inv, args.output)
    print(f"Waves: {inv.waves}")
    print(f"Evidence: {len(inv.evidence)}")
    print(f"Candidates: {len(inv.candidates)}")
    print(f"JSON: {paths[0]}")
    print(f"Markdown: {paths[1]}")


if __name__ == "__main__":
    main()
