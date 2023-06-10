#!/bin/bash

project_id=$GCP_PROJECT_ID
topic_name=$TOPIC_NAME

while true; do
    message="Hello, Pub/Sub!"
    gcloud pubsub topics publish ${topic_name} \
    --message "${message}" \
    --project ${project_id}
    sleep 1
done