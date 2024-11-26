import json
import logging
from logging import handlers
import time

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer, admin, errors

# Logging Parameters
logger = logging.getLogger(__name__)
file_handler = handlers.RotatingFileHandler("katana.log", maxBytes=10000, backupCount=5)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
stream_formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(stream_formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# NOTE: It is required to have global parameters for kafka objects
consumer, producer, topic = None, None, None


def create_consumer(topic_name, bootstrap_servers=None):
    global consumer

    bootstrap_servers = bootstrap_servers or ["kafka:19092"]
    # Create the kafka consumer
    tries = 30
    exit = False
    while not exit:
        try:
            consumer = KafkaConsumer(
                topic_name,
                bootstrap_servers=bootstrap_servers,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                auto_commit_interval_ms=10000,
                group_id="katana-mngr-group",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            )
        except errors.NoBrokersAvailable as KafkaError:
            if tries > 0:
                tries -= 1
                logger.warning(f"Kafka not ready yet. Tries remaining: {tries}")
                time.sleep(5)
            else:
                logger.error(KafkaError)
        else:
            logger.info("New consumer")
            exit = True
            tries = 30
    return consumer


def create_producer(bootstrap_servers=None):
    global producer

    bootstrap_servers = bootstrap_servers or ["kafka:19092"]
    # Create the kafka producer
    tries = 30
    exit = False
    while not exit:
        try:
            producer = KafkaProducer(bootstrap_servers=bootstrap_servers, value_serializer=lambda m: json.dumps(m).encode("utf-8"),)
        except errors.NoBrokersAvailable as KafkaError:
            if tries > 0:
                tries -= 1
                logger.warning(f"Kafka not ready yet. Tries remaining: {tries}")
                time.sleep(5)
            else:
                logger.error(KafkaError)
        else:
            logger.info("New producer")
            exit = True
            tries = 30
    return producer


def create_topic(topic_name, bootstrap_servers=None):
    global topic

    bootstrap_servers = bootstrap_servers or ["kafka:19092"]
    # Create the kafka topic
    tries = 30
    exit = False
    while not exit:
        try:
            try:
                topic = admin.NewTopic(name=topic_name, num_partitions=1, replication_factor=1)
                broker = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
                broker.create_topics([topic])
            except errors.TopicAlreadyExistsError:
                logger.warning("Topic exists already")
            else:
                logger.info("New topic")
        except errors.NoBrokersAvailable as KafkaError:
            if tries > 0:
                tries -= 1
                logger.warning(f"Kafka not ready yet. Tries remaining: {tries}")
                time.sleep(5)
            else:
                logger.error(KafkaError)
        else:
            exit = True
            tries = 30
