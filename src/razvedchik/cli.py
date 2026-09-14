import argparse
from .agent import Agent
from .report import write_reports


MODES = ["fio", "username", "nickname", "phone", "email", "combined"]


def main() -> None:
    p = argparse.ArgumentParser(description="Разведчик — autonomous OSINT agent")
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--waves", type=int, default=4)
    p.add_argument("--per-query", type=int, default=8)
    p.add_argument("--output", default="reports")
    args = p.parse_args()
    inv = Agent(args.mode, args.query, args.waves, args.per_query).run()
    paths = write_reports(inv, args.output)
    print(f"Waves: {inv.waves}")
    print(f"Evidence: {len(inv.evidence)}")
    print(f"Candidates: {len(inv.candidates)}")
    print(f"Source runs: {len(inv.source_runs)}")
    print(f"JSON: {paths[0]}")
    print(f"Markdown: {paths[1]}")


if __name__ == "__main__":
    main()
