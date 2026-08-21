"""Run a traditional pull-worker for local Pub/Sub emulator testing."""

import asyncio
import os
import signal
import sys
from pathlib import Path
import logging
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import pubsub_v1
from google.api_core.exceptions import AlreadyExists

from app.config.settings import Settings
from app.infrastructure.firestore import create_firestore_client
from app.repositories.firestore import FirestoreRepositoryStore
from app.worker import process_event_async
from app.infrastructure.gemini import GeminiSiteInterpreter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ogaforeman.pull_worker")


def main() -> None:
    settings = Settings()

    if not os.environ.get("PUBSUB_EMULATOR_HOST"):
        logger.warning("PUBSUB_EMULATOR_HOST is not set! You are connecting to live Pub/Sub.")

    project_id = settings.google_cloud_project
    topic_id = settings.pubsub_site_events_topic
    subscription_id = settings.pubsub_worker_subscription

    if not project_id or not topic_id or not subscription_id:
        logger.error(
            "GOOGLE_CLOUD_PROJECT, PUBSUB_SITE_EVENTS_TOPIC, and "
            "PUBSUB_WORKER_SUBSCRIPTION must be set in .env"
        )
        sys.exit(1)

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(project_id, topic_id)
    subscription_path = subscriber.subscription_path(project_id, subscription_id)

    try:
        publisher.create_topic(request={"name": topic_path})
        logger.info(f"Created topic: {topic_path}")
    except AlreadyExists:
        logger.info(f"Topic {topic_path} already exists.")

    try:
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
        logger.info(f"Created subscription: {subscription_path}")
    except AlreadyExists:
        logger.info(f"Subscription {subscription_path} already exists.")

    client = create_firestore_client(settings)
    store = FirestoreRepositoryStore(client)
    interpreter = GeminiSiteInterpreter(settings) if not settings.use_fake_model else None

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        logger.info(f"Received message {message.message_id}")

        async def process() -> None:
            try:
                await process_event_async(
                    message.data,
                    store=store,
                    settings=settings,
                    site_interpreter=interpreter,
                )
                message.ack()
                logger.info(f"Acked message {message.message_id}")
            except Exception as e:
                logger.error(f"Error processing message {message.message_id}: {e}")
                message.nack()

        asyncio.run(process())

    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    logger.info(f"Listening for messages on {subscription_path}...\n")

    def shutdown(sig: int, frame: Any) -> None:
        logger.info("Shutting down worker...")
        streaming_pull_future.cancel()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    with subscriber:
        try:
            streaming_pull_future.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Pull worker failed: {e}")


if __name__ == "__main__":
    main()
