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
from yoda.mind.perception.perception import Perception
from yoda.mind.cognition import CognitionProvider
from yoda.mind.mind import Mind
from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.memory.data.emotional_state import EmotionalState
from yoda.mind.affect import AffectProvider
from yoda.mind.agent.agent_provider import AgentProvider
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.tools.ask_user_tool import AskUserTool
from yoda.mind.agent.tools.job_keys import active_jobs_key
from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool
from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool
from yoda.mind.job_dispatcher import JobDispatcher
from yoda.mind.agent.tools.list_jobs_tool import ListJobsTool
from yoda.mind.agent.tools.cancel_job_tool import CancelJobTool
from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
from yoda.embodiment.telegram_bot import TelegramBot
from yoda.api.storage_api import StorageApi
from yoda.api.scheduler_api import SchedulerApi
from yoda.api.speech_api import SpeechApi
from yoda.api.llm_api import LLMApi
from yoda.api.openrouter_api import OpenRouterApi
from yoda.api.tavily_api import TavilyApi
from yoda.api.pixazo_api import PixazoApi
from yoda.mind.agent.tools.get_user_data_tool import GetUserDataTool
from yoda.mind.agent.tools.delete_user_data_tool import DeleteUserDataTool
from yoda.mind.agent.tools.web_extract_tool import WebExtractTool
from yoda.mind.agent.tools.web_search_tool import WebSearchTool
from yoda.mind.agent.tools.image_to_text_tool import ImageToTextTool
from yoda.mind.agent.tools.text_to_image_tool import TextToImageTool
from yoda.mind.agent.tools.send_picture_tool import SendPictureTool
from yoda.mind.agent.skills.catalog import SkillCatalog


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

    try:
        agent_settings = settings_json["agent"]
        agent_model_name = agent_settings["model_name"]
        tavily_api_key = (
            agent_settings["tools"]["web_search"]["tavily_api_key"]
        )
    except KeyError as e:
        raise ValueError(
            f"Settings missing agent key: {e.args[0]}") from e

    llm_api = LLMApi(api_key=language_api_key)
    language_provider = LanguageProvider(
        settings=language_settings, llm_api=llm_api)
    agent_language_settings = {
        **language_settings,
        "model_name": agent_model_name,
    }
    agent_language_provider = LanguageProvider(
        settings=agent_language_settings, llm_api=llm_api)
    vision_backend: OpenRouterApi | LLMApi
    if vision_settings.get("provider", "mistral") == "openrouter":
        vision_base = vision_settings.get(
            "base_url", "https://openrouter.ai/api/v1")
        vision_backend = OpenRouterApi(
            api_key=vision_api_key, base_url=vision_base)
    else:
        vision_backend = LLMApi(api_key=vision_api_key)
    vision_provider = VisionProvider(
        settings=vision_settings, chat_backend=vision_backend)
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

    tavily_api = TavilyApi(api_key=tavily_api_key)

    try:
        text_to_image_settings = agent_settings["tools"]["text_to_image"]
        pixazo_api_key = text_to_image_settings["pixazo_api_key"]
        gateway_url = text_to_image_settings["gateway_url"]
    except KeyError as e:
        raise ValueError(
            f"Settings missing text_to_image key: {e.args[0]}") from e

    async def periodic_job_cleanup() -> None:
        while True:
            await asyncio.sleep(24 * 60 * 60)
            try:
                await reconcile_active_jobs(storage_api, scheduler_api)
            except Exception:
                logger.warning("Periodic job cleanup failed", exc_info=True)

    periodic_cleanup_holder: dict[str, asyncio.Task | None] = {"task": None}

    async def on_post_stop(_application) -> None:
        logger.info("post_stop: started")
        t = periodic_cleanup_holder.get("task")
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            logger.info("post_stop: periodic job cleanup task cancelled")
        elif t is not None:
            logger.info("post_stop: periodic job cleanup task already finished")

        try:
            await body.flush_pending_batches()
            logger.info("post_stop: pending batches flushed")
        except Exception:
            logger.exception("post_stop: failed to flush pending batches")

        try:
            scheduler_api.shutdown()
            logger.info("post_stop: scheduler shut down")
        except Exception:
            logger.exception("post_stop: failed to shut down scheduler")

        try:
            await memory_provider.save_conversation_stash()
            logger.info("post_stop: conversation stash save finished")
        except Exception:
            logger.exception("post_stop: failed to save conversation stash")

    body = TelegramBot(telegram_settings, args.test, post_stop=on_post_stop)

    async def send_picture_to_chat(chat_id: int, file_path: str) -> None:
        await body.telegram_api.send_photo(
            body.bot, chat_id, photo_path=file_path)

    pixazo_api = PixazoApi(gateway_url=gateway_url, api_key=pixazo_api_key)
    skills_dir = Path(__file__).parent / "mind" / "agent" / "skills"

    tools = [
        AskUserTool(),
        ScheduleMessageTool(scheduler_api=scheduler_api, storage_api=storage_api),
        ScheduleTaskTool(
            scheduler_api=scheduler_api,
            storage_api=storage_api,
            skills_dir=skills_dir,
        ),
        ListJobsTool(storage_api=storage_api),
        CancelJobTool(scheduler_api=scheduler_api, storage_api=storage_api),
        UpdateProfileTool(memory_provider=memory_provider),
        WebSearchTool(tavily_api=tavily_api),
        WebExtractTool(tavily_api=tavily_api),
        GetUserDataTool(storage_api=storage_api),
        DeleteUserDataTool(
            storage_api=storage_api,
            scheduler_api=scheduler_api,
            memory_provider=memory_provider,
        ),
        TextToImageTool(pixazo_api=pixazo_api),
        ImageToTextTool(vision_provider=vision_provider),
        SendPictureTool(send_photo=send_picture_to_chat),
    ]
    session_provider = AgentSessionProvider(storage_api=storage_api)
    public_skill_descriptions = [
        s.description for s in SkillCatalog.public_summaries(
            SkillCatalog.load_catalog(skills_dir))
    ]

    agent_provider = AgentProvider(
        language_provider=agent_language_provider,
        tools=tools,
        skills_dir=skills_dir,
        session_provider=session_provider,
    )

    perception = Perception(
        audio_provider=audio_provider,
        vision_provider=vision_provider,
    )
    cognition_provider = CognitionProvider(language_provider=language_provider)

    mind = Mind(
        language_provider=language_provider,
        perception=perception,
        memory_provider=memory_provider,
        affect_provider=affect_provider,
        cognition_provider=cognition_provider,
        agent_provider=agent_provider,
        public_skill_descriptions=public_skill_descriptions,
    )

    job_dispatcher = JobDispatcher(
        storage_api=storage_api,
        scheduler_api=scheduler_api,
        mind=mind,
    )
    scheduler_api.set_fire_callback(job_dispatcher.fire)

    async def cleanup_job_metadata(chat_id: int, job_id: str) -> None:
        await storage_api.hdel(active_jobs_key(chat_id), job_id)

    scheduler_api.set_cleanup_callback(cleanup_job_metadata)

    async def on_app_start(application):
        await memory_provider.restore_conversation_stash()
        scheduler_api.start()
        await asyncio.sleep(2)  # let APScheduler process misfired jobs
        await reconcile_active_jobs(storage_api, scheduler_api)
        periodic_cleanup_holder["task"] = asyncio.create_task(periodic_job_cleanup())

    body.wake_up(mind, on_start=on_app_start)
    logger.info("main(): returned after run_polling (process should exit)")


if __name__ == "__main__":
    main()
    