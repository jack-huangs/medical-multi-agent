import argparse
import importlib
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MDAGENTS_ROOT = ROOT / "external" / "MDAgents"


def check_import(module_name):
    importlib.import_module(module_name)
    print(f"OK import {module_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Run offline health checks for the MDAgents reproduction environment."
    )
    parser.add_argument(
        "--check-env-name",
        action="store_true",
        help="Verify that the DeepSeek API key variable name is documented, without reading its value.",
    )
    args = parser.parse_args()

    if not MDAGENTS_ROOT.exists():
        raise SystemExit(f"Missing upstream source directory: {MDAGENTS_ROOT}")

    sys.path.insert(0, str(MDAGENTS_ROOT))
    for module_name in ["openai", "google.generativeai", "tqdm", "prettytable", "termcolor", "pptree", "climage", "utils"]:
        check_import(module_name)

    if args.check_env_name:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        if "DEEPSEEK_API_KEY=" not in example:
            raise SystemExit(".env.example does not document DEEPSEEK_API_KEY")
        print("OK .env.example documents DEEPSEEK_API_KEY")
        print("OK no API key value was read")

    print(f"OK upstream source: {MDAGENTS_ROOT}")


if __name__ == "__main__":
    main()
