import argparse
import json
import logging
import os
import sys
from pathlib import Path

# When run as script (e.g. from launch.json), project root must be on path so "yoda" package resolves.
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
  sys.path.insert(0, str(_project_root))

os.environ["PATH"] += os.pathsep + str(_project_root / "bin")

from yoda.mind.mind import Mind
from yoda.embodiment.telegram_bot import TelegramBot


def parse_arguments():
  global test_mode
  parser = argparse.ArgumentParser(
      prog='python yoda\\main.py',
      description='Yoda\'s presence as a Telegram chat bot')
  parser.add_argument('-t', '--test', action='store_true',
                      help='run bot with test Telegram account')

  return parser.parse_args()


def main() -> None:
  logging.getLogger("httpx").setLevel(logging.WARNING)
  logging.basicConfig(
      format="%(asctime)s (%(levelname)s): %(name)s - %(message)s", level=logging.INFO)
  logger = logging.getLogger(__name__)

  args = parse_arguments()
  logger.info(f"Starting with arguments: {args}")

  with open('settings.json', 'r') as settings_file:
    settings_json = json.load(settings_file)

  mind = Mind(settings_json["mind"])
  body = TelegramBot(settings_json["embodiment"]["telegram"], args.test)

  body.wake_up(mind)


if __name__ == "__main__":
  main()
