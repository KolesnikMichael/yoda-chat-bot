import logging
import argparse
import os
import json
from mind._mind import Mind
from embodiment.telegram_bot import TelegramBot

os.environ['PATH'] += os.pathsep + os.path.abspath('bin')

def parse_arguments():
    global test_mode
    parser = argparse.ArgumentParser(
        prog='python yoda\\main.py',
        description='Yoda\'s presence as a Telegram chat bot')
    parser.add_argument('-t', '--test', action='store_true', help='run bot with test Telegram account')

    return parser.parse_args()


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(format="%(asctime)s (%(levelname)s): %(name)s - %(message)s", level=logging.INFO)
    logger = logging.getLogger(__name__)

    args = parse_arguments()
    logger.info("Starting with arguments: %s", args)

    with open('settings.json', 'r') as settings_file:
        settings_json = json.load(settings_file)

    mind = Mind(settings_json["mind"])
    body = TelegramBot(settings_json["embodiment"]["telegram"], args.test)

    body.wake_up(mind)


if __name__ == "__main__":
    main()