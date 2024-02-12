# Event-driven autoscaling with KEDA in GKE

This repository contains the sample application and template files used in the article [Event-Driven Autoscaling in Kubernetes: Harnessing the Power of KEDA](https://www.doit.com/event-driven-autoscaling-in-kubernetes-harnessing-the-power-of-keda/) published on Medium.

## Overview
The purpose of this repository is to provide a reference implementation for event-driven autoscaling in Kubernetes using KEDA. It includes a sample application and the necessary template files to demonstrate the concepts discussed in the article.

# Contents

`app/`: Contains the source code and configuration files for the sample application.

`templates/`: Includes the Kubernetes manifest templates for deploying the application and configuring autoscaling with KEDA.

## Prerequisites

- A GKE cluster with workload identity enabled
- Install [kubectl](https://kubernetes.io/docs/tasks/tools/) and [Helm](https://helm.sh/docs/intro/install/) in your local machine or in the CICD setup

## Setup Pub/Sub resources

Run the below commands to set up a pub/sub topic and subscription.

```
GCP_PROJECT_ID=$(gcloud config get-value project)
TOPIC_NAME=keda-demo-topic
SUBSCRIPTION_NAME=keda-demo-topic-subscription

# Create Topic
gcloud pubsub topics create $TOPIC_NAME --project $GCP_PROJECT_ID

# Create Subscription
gcloud pubsub subscriptions create $SUBSCRIPTION_NAME \
--topic $TOPIC_NAME \
--project $GCP_PROJECT_ID
```

## Setup Workload Identity for KEDA

(GCP Workload Identity)[https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity] allows workloads in GKE clusters to impersonate Identity and Access Management (IAM) service accounts to access Google Cloud services. Workload Identity is the recommended way for workloads running on GKE to access Google Cloud services in a secure and manageable way.

Run the below commands to set up workload identity for KEDA.

```
KEDA_GCP_SERVICE_ACCOUNT=keda-operator
KEDA_NAMESPACE=keda
KEDA_K8S_SERVICE_ACCOUNT=keda-operator

#Create GCP service account
gcloud iam service-accounts create $KEDA_GCP_SERVICE_ACCOUNT \
--project=$GCP_PROJECT_ID

#Create IAM role bindings
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
--member "serviceAccount:$KEDA_GCP_SERVICE_ACCOUNT@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
--role "roles/monitoring.viewer"

#Allow kubernetes service account to impersonate GCP service account
gcloud iam service-accounts add-iam-policy-binding $KEDA_GCP_SERVICE_ACCOUNT@$GCP_PROJECT_ID.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:$GCP_PROJECT_ID.svc.id.goog[$KEDA_NAMESPACE/$KEDA_K8S_SERVICE_ACCOUNT
```

## Install KEDA

Below are the various options which can be used to install KEDA on Kubernetes Cluster.

- (Helm charts)[https://keda.sh/docs/2.10/deploy/#helm]
- (Operator Hub)[https://keda.sh/docs/2.10/deploy/#operatorhub]
- (YAML declarations)[https://keda.sh/docs/2.10/deploy/#yaml]

We will use Helm Chart to deploy KEDA in the GKE cluster.

- Add and update the Helm repo.
```
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
```

- Install the latest KEDA helm chart.
```
helm upgrade -install keda kedacore/keda \
--namespace keda \
--set 'serviceAccount.annotations.iam\.gke\.io\/gcp-service-account'="$KEDA_SERVICE_ACCOUNT@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
--create-namespace \
--debug \
--wait
```

The KEDA webhook calls are served over port 9443, So ensure any firewall rule between the control plan -> node allows the request over port 9443. In GKE, the auto-generated firewall rules only allow communication over ports 443,10250, and you need to create a new firewall to allow the over port 9443.

Sample gcloud firewall rule command.

```
gcloud compute firewall-rules create allow-api-server-to-keda-webhook \
--description="Allow kubernetes api server to keda webhook call on worker nodes TCP port 9443" \
--direction=INGRESS \
--priority=1000 \
--network=$VPC-NETWORK-NAME \
--action=ALLOW \
--rules=tcp:9443 \
--source-ranges=$CONTROL-PLANE-IP-RANGE \
--target-tags=$NETWORK-TAGS-ASSIGNED-TO-NODES
```

## Deploy the sample application

Set up workload identity for the sample application to consume the messages from the pub/sub subscription.

```
SAMPLE_APP_GCP_SERVICE_ACCOUNT=keda-demo
SAMPLE_APP_NAMESPACE=default
SAMPLE_APP_K8S_SERVICE_ACCOUNT=keda-demo

#Create GCP service account
gcloud iam service-accounts create $SAMPLE_APP_GCP_SERVICE_ACCOUNT \
--project=$GCP_PROJECT_ID

#Create IAM role bindings
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
--member "serviceAccount:$SAMPLE_APP_GCP_SERVICE_ACCOUNT@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
--role "roles/pubsub.subscriber"

#Allow kubernetes service account to impersonate GCP service account
gcloud iam service-accounts add-iam-policy-binding $SAMPLE_APP_GCP_SERVICE_ACCOUNT@$GCP_PROJECT_ID.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:$GCP_PROJECT_ID.svc.id.goog[$KEDA_NAMESPACE/$KEDA_SERVICE_ACCOUNT]"
```

Deploy the sample application to the GKE cluster.

```
cat <<EOF | kubectl apply -f -
---
apiVersion: v1
kind: ServiceAccount
metadata:
  annotations:
    iam.gke.io/gcp-service-account: keda-demo@$GCP_PROJECT_ID.iam.gserviceaccount.com
  name: keda-demo
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: keda-demo
spec:
  selector:
    matchLabels:
      app: keda-demo
  replicas: 1
  template:
    metadata:
      labels:
        app: keda-demo
    spec:
      serviceAccountName: keda-demo
      containers:
      - image: simbu1290/keda-demo:v1
        name: consumer
        env:
        - name: PUB_SUB_PROJECT
          value: $GCP_PROJECT_ID
        - name: PUB_SUB_TOPIC
          value: "keda-demo-topic"
        - name: PUB_SUB_SUBSCRIPTION
          value: "keda-demo-topic-subscription"
EOF
```

## Deploy KEDA Event Scaler

KEDA seamlessly integrates with various (Scalers)[https://keda.sh/docs/2.10/scalers/] (event sources) and utilizes Custom Resources (CRDs) to specify the necessary/desired scaling actions and parameters. KEDA monitors the event source and feeds that data to Horizontal Pod Autoscaler (HPA) to drive the rapid scale of a resource.

Here we will use (Google Cloud Platform Pub/Sub)[https://keda.sh/docs/2.10/scalers/gcp-pub-sub/] event scaler to demonstrate Auto Scaling. The scaling relationship between an event source and a specific workload (i.e., Deployment, StatefulSet) is configured using the (ScaledObject)[https://keda.sh/docs/2.10/concepts/scaling-deployments/#scaledobject-spec] Custom Resource Definition.

(TriggerAuthentication)[https://keda.sh/docs/2.10/concepts/authentication/#re-use-credentials-and-delegate-auth-with-triggerauthentication] allows you to describe authentication parameters separate from the (ScaledObject)[https://keda.sh/docs/2.10/concepts/scaling-deployments/#scaledobject-spec] and the deployment containers. It also enables more advanced authentication methods like pod identity and authentication re-use.

Deploy the below resources for autoscaling, and KEDA will perform scaling based on the number of unacknowledged messages in the subscription.

```
cat <<EOF | kubectl apply -f -
---
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: keda-demo-trigger-auth-gcp-credentials
spec:
  podIdentity:
    provider: gcp
---
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: keda-demo-pubsub-scaledobject
spec:
  scaleTargetRef:
    apiVersion: apps/v1 # Optional. Default: apps/v1
    kind: Deployment    # Optional. Default: Deployment
    name: keda-demo     # Mandatory. Must be in the same namespace as the ScaledObject
  pollingInterval: 5    # Optional. Default: 30 seconds
  minReplicaCount: 0    # Optional. Default: 0
  maxReplicaCount: 10   # Optional. Default: 100
  triggers:
  - type: gcp-pubsub
    authenticationRef:
      kind: TriggerAuthentication
      name: keda-demo-trigger-auth-gcp-credentials
    metadata:
      mode: "SubscriptionSize" # Optional - Default is SubscriptionSize - SubscriptionSize or OldestUnackedMessageAge
      value: "5" # Optional - Default is 5 for SubscriptionSize | Default is 10 for OldestUnackedMessageAge
      subscriptionName: "keda-demo-topic-subscription" # Mandatory
EOF
```

## Test the setup

Now we can send some messages and see if our deployment scales! Use the script `generate-message.sh` to send messages to the queue and monitor the deployment.
KEDA will automatically scale the number of replicas to zero when no messages are available in the queue.

Use the below script to publish test messages to the topic and observe the scaling actions performed by HPA based on the metrics provided by KEDA.

<iframe src="https://player.vimeo.com/video/834982934?h=b121a43264" width="640" height="399" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>
<p><a href="https://vimeo.com/834982934">Keda scaling demo</a> from <a href="https://vimeo.com/user184559895">Chimbu Chinnadurai</a> on <a href="https://vimeo.com">Vimeo</a>.</p>