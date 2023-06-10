import os
from google.cloud import pubsub_v1
from concurrent.futures import TimeoutError
import time

PUB_SUB_TOPIC = os.environ['PUB_SUB_TOPIC']
PUB_SUB_PROJECT = os.environ['PUB_SUB_PROJECT']
PUB_SUB_SUBSCRIPTION = os.environ['PUB_SUB_SUBSCRIPTION']

# Pub/Sub consumer timeout
timeout = 3.0

def process_payload(message):
    print(f"Received {message.data}.")
    message.ack()

def consume_message(project, subscription, process_payload, period):
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(project, subscription)
        print(f"Listening for messages on {subscription_path}..\n")
        streaming_pull_future = subscriber.subscribe(subscription_path, callback=process_payload)
        # Wrap subscriber in a 'with' block to automatically call close() when done.
        with subscriber:
            try:
                streaming_pull_future.result(timeout=period)
            except TimeoutError:
                streaming_pull_future.cancel()

while(True):
    consume_message(PUB_SUB_PROJECT, PUB_SUB_SUBSCRIPTION, process_payload, timeout)
    time.sleep(3)