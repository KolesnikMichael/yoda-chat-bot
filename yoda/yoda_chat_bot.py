import argparse
import logging
import json
from mind._mind import Mind
from embodiment.telegram_bot import TelegramBot

def parse_arguments():
    global test_mode
    parser = argparse.ArgumentParser(
        prog='python yoda\\main.py',
        description='Yoda\'s presence as a Telegram chat bot')
    parser.add_argument('-t', '--test', action='store_true', help='run bot with test Telegram account')

    return parser.parse_args()


def main() -> None:
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)

    args = parse_arguments()

    with open('settings.json', 'r') as settings_file:
        settings_json = json.load(settings_file)

    mind = Mind(settings_json["mind"], logger)
    body = TelegramBot(settings_json["embodiment"]["telegram"], logger, args.test)

    body.wake_up(mind)


if __name__ == "__main__":
    main()