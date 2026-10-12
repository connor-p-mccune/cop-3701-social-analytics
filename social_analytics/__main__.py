"""Command-line entry point: python -m social_analytics <command> [options]."""

import sys

COMMANDS = {
    "preprocess": ("social_analytics.etl.preprocess", "sample Sentiment140 into data/*.csv"),
    "init-db": ("social_analytics.sql_runner", "create the schema (drops existing tables)"),
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("usage: python -m social_analytics <command> [options]\n\ncommands:")
        for name, (_module, help_text) in COMMANDS.items():
            print(f"  {name:<12} {help_text}")
        sys.exit(0 if len(sys.argv) < 2 else 2)

    module_name, _help = COMMANDS[sys.argv[1]]
    module = __import__(module_name, fromlist=["main"])
    module.main(sys.argv[2:])


if __name__ == "__main__":
    main()
