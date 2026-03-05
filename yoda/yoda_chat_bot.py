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

from yoda.api.llm_api import LLMApi
from yoda.api.speech_api import SpeechApi
from yoda.api.storage_api import StorageApi
from yoda.embodiment.telegram_bot import TelegramBot
from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.mind import Mind
from yoda.mind.perception.audio import AudioProvider
from yoda.mind.perception.language import LanguageProvider
from yoda.mind.perception.vision import VisionProvider


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

  try:
    mind_settings = settings_json["mind"]
  except KeyError as e:
    raise ValueError("settings.json is missing required 'mind' section") from e

  try:
    embodiment_settings = settings_json["embodiment"]
    telegram_settings = embodiment_settings["telegram"]
  except KeyError as e:
    raise ValueError("settings.json is missing required 'embodiment.telegram' section") from e
  perception_settings = mind_settings["perception"]
  language_settings = perception_settings["language"]
  vision_settings = perception_settings["vision"]
  audio_settings = perception_settings["audio"]

  llm_api = LLMApi(api_key=language_settings["api_key"])
  language_provider = LanguageProvider(settings=language_settings, llm_api=llm_api)
  vision_provider = VisionProvider(settings=vision_settings, llm_api=llm_api)

  audio_provider = AudioProvider(
      speech_api=SpeechApi(),
      default_language=audio_settings["default_language"],
  )

  memory_settings = mind_settings["memory"]
  storage_api = StorageApi(
      host=memory_settings.get("redis_host", "localhost"),
      port=memory_settings.get("redis_port", 6379),
      db=memory_settings.get("redis_db", 0),
  )
  memory_provider = MemoryProvider(storage_api=storage_api)

  mind = Mind(
      mind_settings,
      memory_provider=memory_provider,
      language_provider=language_provider,
      audio_provider=audio_provider,
      vision_provider=vision_provider,
  )
  body = TelegramBot(telegram_settings, args.test)

  body.wake_up(mind)


if __name__ == "__main__":
  main()
