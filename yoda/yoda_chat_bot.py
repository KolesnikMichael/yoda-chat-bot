import asyncio
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

from yoda.mind.perception.vision import VisionProvider
from yoda.mind.perception.language import LanguageProvider
from yoda.mind.perception.audio import AudioProvider
from yoda.mind.mind import Mind
from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.memory.data.emotional_state import EmotionalState
from yoda.mind.affect import AffectProvider
from yoda.mind.agent.agent_provider import AgentProvider
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.tools.ask_user_tool import AskUserTool
from yoda.mind.agent.tools.scheduler_tool import SchedulerTool
from yoda.mind.agent.tools.list_jobs_tool import ListJobsTool
from yoda.mind.agent.tools.cancel_job_tool import CancelJobTool
from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
from yoda.embodiment.telegram_bot import TelegramBot
from yoda.api.storage_api import StorageApi
from yoda.api.scheduler_api import SchedulerApi
from yoda.api.speech_api import SpeechApi
from yoda.api.llm_api import LLMApi


logger = logging.getLogger(__name__)


async def reconcile_active_jobs(storage_api: StorageApi, scheduler_api: SchedulerApi) -> int:
    live_ids = scheduler_api.get_job_ids()
    all_keys = await storage_api.keys("active_jobs:*")
    removed = 0
    for key in all_keys:
        entries = await storage_api.hgetall(key)
        for job_id in entries:
            if job_id not in live_ids:
                await storage_api.hdel(key, job_id)
                removed += 1
    if removed:
        logger.info(f"Reconciled active_jobs: removed {removed} stale entries")
    return removed


def parse_arguments():
    global test_mode
    parser = argparse.ArgumentParser(
        prog='python yoda\\main.py',
        description='Yoda\'s presence as a Telegram chat bot')
    parser.add_argument('-t', '--test', action='store_true',
                        help='run bot with test Telegram account')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='turn on debug logging')

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.debug:
        logging.basicConfig(
            format="%(asctime)s (%(levelname)s): %(name)s - %(message)s", level=logging.DEBUG)
    elif args.test:
        logging.basicConfig(
            format="%(asctime)s (%(levelname)s): %(name)s - %(message)s", level=logging.INFO)
    else:
        logging.basicConfig(
            format="%(asctime)s (%(levelname)s): %(name)s - %(message)s", level=logging.INFO, filename="/var/log/yodabot/yodabot.log")
  
    logger.info(f"Starting with arguments: {args}")

    with open('settings.json', 'r') as settings_file:
        settings_json = json.load(settings_file)

    try:
        embodiment_settings = settings_json["embodiment"]
        telegram_settings = embodiment_settings["telegram"]
        mind_settings = settings_json["mind"]
        perception_settings = mind_settings["perception"]
        language_settings = perception_settings["language"]
        vision_settings = perception_settings["vision"]
        language_api_key = language_settings["api_key"]
        vision_api_key = vision_settings["api_key"]
        audio_settings = perception_settings["audio"]
        default_language = audio_settings["default_language"]
        memory_settings = mind_settings["memory"]
        emotions_settings = mind_settings["emotions"]
    except KeyError as e:
        missing_key = e.args[0]
        raise ValueError(
            f"Settings missing required key: {missing_key}") from e

    language_provider = LanguageProvider(
        settings=language_settings, llm_api=LLMApi(api_key=language_api_key))
    vision_provider = VisionProvider(
        settings=vision_settings, llm_api=LLMApi(api_key=vision_api_key))
    audio_provider = AudioProvider(
        speech_api=SpeechApi(), default_language=default_language)
    storage_api = StorageApi(
        host=memory_settings.get("redis_host", "localhost"),
        port=memory_settings.get("redis_port", 6379),
        db=memory_settings.get("redis_db", 0),
    )
    memory_provider = MemoryProvider(storage_api=storage_api)
    affect_provider = AffectProvider(EmotionalState(**emotions_settings))

    scheduler_api = SchedulerApi(
        redis_host=memory_settings.get("redis_host", "localhost"),
        redis_port=memory_settings.get("redis_port", 6379),
        redis_db=memory_settings.get("redis_db", 0),
    )

    tools = [
        AskUserTool(),
        SchedulerTool(scheduler_api=scheduler_api, storage_api=storage_api),
        ListJobsTool(storage_api=storage_api),
        CancelJobTool(scheduler_api=scheduler_api, storage_api=storage_api),
        UpdateProfileTool(memory_provider=memory_provider),
    ]
    skills_dir = Path(__file__).parent / "mind" / "agent" / "skills"
    session_provider = AgentSessionProvider(storage_api=storage_api)

    agent_provider = AgentProvider(
        language_provider=language_provider,
        tools=tools,
        skills_dir=skills_dir,
        session_provider=session_provider,
    )

    mind = Mind(
        language_provider=language_provider,
        vision_provider=vision_provider,
        audio_provider=audio_provider,
        memory_provider=memory_provider,
        affect_provider=affect_provider,
        agent_provider=agent_provider,
    )

    scheduler_api.set_delivery_callback(mind.deliver_scheduled_reminder)

    async def cleanup_job_metadata(chat_id: int, job_id: str) -> None:
        await storage_api.hdel(f"active_jobs:{chat_id}", job_id)

    scheduler_api.set_cleanup_callback(cleanup_job_metadata)

    async def periodic_job_cleanup() -> None:
        while True:
            await asyncio.sleep(24 * 60 * 60)
            try:
                await reconcile_active_jobs(storage_api, scheduler_api)
            except Exception:
                logger.warning("Periodic job cleanup failed", exc_info=True)

    async def on_app_start(_application):
        scheduler_api.start()
        await asyncio.sleep(2) # let APScheduler process misfired jobs
        await reconcile_active_jobs(storage_api, scheduler_api)
        asyncio.create_task(periodic_job_cleanup())

    body = TelegramBot(telegram_settings, args.test)

    body.wake_up(mind, on_start=on_app_start)


if __name__ == "__main__":
    main()
    