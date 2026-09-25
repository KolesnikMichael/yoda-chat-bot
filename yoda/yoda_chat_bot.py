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
from yoda.mind.memory.data.chat_compression_settings import ChatCompressionSettings
from yoda.mind.memory.data.emotional_state import EmotionalState
from yoda.mind.affect import AffectProvider
from yoda.mind.agent.agent import Agent
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
from yoda.api.inference.backends import build_chat_backend, build_embeddings_api
from yoda.api.inference.catalog import InferenceCatalogCore
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
from yoda.mind.data.maintenance_settings import MaintenanceSettings
from yoda.mind.maintenance import Maintenance
from yoda.mind.memory.data.summarizer_settings import SummarizerSettings
from yoda.mind.memory.data.summary_store_settings import EmbeddingsSettings, SummaryStoreSettings
from yoda.mind.memory.summarizer import SummarizerProvider
from yoda.mind.memory.embedding import EmbeddingProvider
from yoda.mind.memory.vector import VectorProvider


logger = logging.getLogger(__name__)


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

    configured = InferenceCatalogCore.resolve_configured(settings_json)

    try:
        embodiment_settings = settings_json["embodiment"]
        telegram_settings = embodiment_settings["telegram"]
        mind_settings = settings_json["mind"]
        perception_settings = mind_settings["perception"]
        audio_settings = perception_settings["audio"]
        default_language = audio_settings["default_language"]
        memory_settings = mind_settings["memory"]
        emotions_settings = mind_settings["emotions"]
        maintenance_settings = MaintenanceSettings.from_dict(mind_settings["maintenance"])
        chat_compression_settings = ChatCompressionSettings.from_dict(
            memory_settings["chat_compression"]
        )
        summary_store_settings = SummaryStoreSettings.from_dict(
            memory_settings["summary_store"]
        )
    except KeyError as e:
        missing_key = e.args[0]
        raise ValueError(
            f"Settings missing required key: {missing_key}") from e

    try:
        agent_settings = settings_json["agent"]
        tavily_api_key = (
            agent_settings["tools"]["web_search"]["tavily_api_key"]
        )
    except KeyError as e:
        raise ValueError(
            f"Settings missing agent key: {e.args[0]}") from e

    debug_log_dir = Path("logs") if args.debug else None
    language_provider = LanguageProvider(
        {"model_name": configured.language.model_name},
        build_chat_backend(configured.language, debug_log_dir=debug_log_dir),
    )
    agent_language_provider = LanguageProvider(
        {"model_name": configured.agent.model_name},
        build_chat_backend(configured.agent, debug_log_dir=debug_log_dir),
    )
    vision_provider = VisionProvider(
        {"model_name": configured.vision.model_name},
        build_chat_backend(configured.vision, debug_log_dir=debug_log_dir),
        configured.vision.backend,
    )
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

    summarizer_provider = SummarizerProvider(
        build_chat_backend(configured.summarizer, debug_log_dir=debug_log_dir),
        SummarizerSettings(model_name=configured.summarizer.model_name),
    )

    embedding_provider = EmbeddingProvider(
        embeddings_api=build_embeddings_api(configured.embeddings),
        settings=EmbeddingsSettings(model_name=configured.embeddings.model_name),
    )
    vector_provider = VectorProvider(settings=summary_store_settings)

    maintenance = Maintenance(
        storage_api=storage_api,
        scheduler_api=scheduler_api,
        memory_provider=memory_provider,
        compression_settings=chat_compression_settings,
        maintenance_settings=maintenance_settings,
        summarizer_provider=summarizer_provider,
        embedding_provider=embedding_provider,
        vector_provider=vector_provider,
    )

    tavily_api = TavilyApi(api_key=tavily_api_key)

    try:
        text_to_image_settings = agent_settings["tools"]["text_to_image"]
        pixazo_api_key = text_to_image_settings["pixazo_api_key"]
        gateway_url = text_to_image_settings["gateway_url"]
    except KeyError as e:
        raise ValueError(
            f"Settings missing text_to_image key: {e.args[0]}") from e

    async def on_post_stop(_application) -> None:
        logger.info("post_stop: started")
        await maintenance.stop()

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

    agent = Agent(
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
        agent=agent,
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
        await maintenance.run_initial_pass()
        maintenance.start()

    body.wake_up(mind, on_start=on_app_start)
    logger.info("main(): returned after run_polling (process should exit)")


if __name__ == "__main__":
    main()
    