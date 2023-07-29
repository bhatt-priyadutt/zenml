---
description: Orchestrating your pipelines to run on Kubernetes clusters.
---

# Kubernetes Orchestrator

The Kubernetes orchestrator is an [orchestrator](orchestrators.md) flavor provided with the ZenML `kubernetes`
integration that runs your pipelines on a [Kubernetes](https://kubernetes.io/) cluster.

{% hint style="warning" %}
This component is only meant to be used within the context of
a [remote ZenML deployment scenario](/docs/book/platform-guide/set-up-your-mlops-platform/deploy-zenml/deploy-zenml.md). 
Usage with a local ZenML deployment may lead to unexpected behavior!
{% endhint %}

### When to use it

You should use the Kubernetes orchestrator if:

* you're looking lightweight way of running your pipelines on Kubernetes.
* you don't need a UI to list all your pipeline runs.
* you're not willing to maintain [Kubeflow Pipelines](kubeflow.md) on your Kubernetes cluster.
* you're not interested in paying for managed solutions like [Vertex](vertex.md).

### How to deploy it

The Kubernetes orchestrator requires a Kubernetes cluster in order to run. There are many ways to deploy a Kubernetes
cluster using different cloud providers or on your custom infrastructure, and we can't possibly cover all of them, but
you can check out our cloud guide

If the above Kubernetes cluster is deployed remotely on the cloud, then another pre-requisite to use this orchestrator
would be to deploy and connect to a 
[remote ZenML server](/docs/book/platform-guide/set-up-your-mlops-platform/deploy-zenml/deploy-zenml.md).

#### Infrastructure Deployment

A Kubernetes orchestrator can be deployed directly from the ZenML CLI:

```shell
zenml orchestrator deploy k8s_orchestrator --flavor=kubernetes ...
```

You can pass other configurations specific to the stack components as key-value arguments. If you don't provide a name,
a random one is generated for you. For more information about how to work use the CLI for this, please refer to the
dedicated documentation section.

### How to use it

To use the Kubernetes orchestrator, we need:

* The ZenML `kubernetes` integration installed. If you haven't done so, run

  ```shell
  zenml integration install kubernetes
  ```
* [Docker](https://www.docker.com) installed and running.
* [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl) installed.
* A [remote artifact store](../artifact-stores/artifact-stores.md) as part of your stack.
* A [remote container registry](../container-registries/container-registries.md) as part of your stack.
* A Kubernetes cluster [deployed](kubernetes.md#how-to-deploy-it)
* [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl) installed and the name of the Kubernetes configuration
  context which points to the target cluster (i.e. run`kubectl config get-contexts` to see a list of available contexts)
  . This is optional (see below).

{% hint style="info" %}
It is recommended that you set
up [a Service Connector](../../../platform-guide/set-up-your-mlops-platform/connect-zenml-to-infrastructure/service-connectors-guide.md)
and use it to connect ZenML Stack Components to the remote Kubernetes cluster, especially If you are using a Kubernetes
cluster managed by a cloud provider like AWS, GCP or Azure, This guarantees that your Stack is fully portable on other
environments and your pipelines are fully reproducible.
{% endhint %}

We can then register the orchestrator and use it in our active stack. This can be done in two ways:

1. If you
   have [a Service Connector](../../../platform-guide/set-up-your-mlops-platform/connect-zenml-to-infrastructure/service-connectors-guide.md)
   configured to access the remote Kubernetes cluster, you no longer need to set the `kubernetes_context` attribute to a
   local `kubectl` context. In fact, you don't need the local Kubernetes CLI at all. You
   can [connect the stack component to the Service Connector](../../../platform-guide/set-up-your-mlops-platform/connect-zenml-to-infrastructure/service-connectors-guide.md#connect-stack-components-to-resources)
   instead:

    ```
    $ zenml orchestrator register <ORCHESTRATOR_NAME> --flavor kubernetes
    Running with active workspace: 'default' (repository)
    Running with active stack: 'default' (repository)
    Successfully registered orchestrator `<ORCHESTRATOR_NAME>`.
    
    $ zenml service-connector list-resources --resource-type kubernetes-cluster -e
    The following 'kubernetes-cluster' resources can be accessed by service connectors configured in your workspace:
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━━━━┓
    ┃             CONNECTOR ID             │ CONNECTOR NAME        │ CONNECTOR TYPE │ RESOURCE TYPE         │ RESOURCE NAMES      ┃
    ┠──────────────────────────────────────┼───────────────────────┼────────────────┼───────────────────────┼─────────────────────┨
    ┃ e33c9fac-5daa-48b2-87bb-0187d3782cde │ aws-iam-multi-eu      │ 🔶 aws         │ 🌀 kubernetes-cluster │ kubeflowmultitenant ┃
    ┃                                      │                       │                │                       │ zenbox              ┃
    ┠──────────────────────────────────────┼───────────────────────┼────────────────┼───────────────────────┼─────────────────────┨
    ┃ ed528d5a-d6cb-4fc4-bc52-c3d2d01643e5 │ aws-iam-multi-us      │ 🔶 aws         │ 🌀 kubernetes-cluster │ zenhacks-cluster    ┃
    ┠──────────────────────────────────────┼───────────────────────┼────────────────┼───────────────────────┼─────────────────────┨
    ┃ 1c54b32a-4889-4417-abbd-42d3ace3d03a │ gcp-sa-multi          │ 🔵 gcp         │ 🌀 kubernetes-cluster │ zenml-test-cluster  ┃
    ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━┛
    
    $ zenml orchestrator connect <ORCHESTRATOR_NAME> --connector aws-iam-multi-us
    Running with active workspace: 'default' (repository)
    Running with active stack: 'default' (repository)
    Successfully connected orchestrator `<ORCHESTRATOR_NAME>` to the following resources:
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━━━━━━┯━━━━━━━━━━━━━━━━━━┓
    ┃             CONNECTOR ID             │ CONNECTOR NAME   │ CONNECTOR TYPE │ RESOURCE TYPE         │ RESOURCE NAMES   ┃
    ┠──────────────────────────────────────┼──────────────────┼────────────────┼───────────────────────┼──────────────────┨
    ┃ ed528d5a-d6cb-4fc4-bc52-c3d2d01643e5 │ aws-iam-multi-us │ 🔶 aws         │ 🌀 kubernetes-cluster │ zenhacks-cluster ┃
    ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━━━┛
    
    # Register and activate a stack with the new orchestrator
    $ zenml stack register <STACK_NAME> -o <ORCHESTRATOR_NAME> ... --set
    ```

2. if you don't have a Service Connector on hand and you don't want
   to [register one](../../../platform-guide/set-up-your-mlops-platform/connect-zenml-to-infrastructure/service-connectors-guide.md#register-service-connectors)
   , the local Kubernetes `kubectl` client needs to be configured with a configuration context pointing to the remote
   cluster. The `kubernetes_context` stack component must also be configured with the value of that context:

    ```shell
    zenml orchestrator register <ORCHESTRATOR_NAME> \
        --flavor=kubernetes \
        --kubernetes_context=<KUBERNETES_CONTEXT>
    
    # Register and activate a stack with the new orchestrator
    zenml stack register <STACK_NAME> -o <ORCHESTRATOR_NAME> ... --set
    ```

{% hint style="info" %}
ZenML will build a Docker image called `<CONTAINER_REGISTRY_URI>/zenml:<PIPELINE_NAME>` which includes your code and use
it to run your pipeline steps in Kubernetes. Check
out [this page](/docs/book/user-guide/advanced-guide/environment-management/containerize-your-pipeline.md) if you want to learn
more about how ZenML builds these images and how you can customize them.
{% endhint %}

You can now run any ZenML pipeline using the Kubernetes orchestrator:

```shell
python file_that_runs_a_zenml_pipeline.py
```

#### Additional configuration

For additional configuration of the Kubernetes orchestrator, you can pass `KubernetesOrchestratorSettings` which allows
you to configure (among others) the following attributes:

* `pod_settings`: Node selectors, affinity, and tolerations to apply to the Kubernetes Pods running your pipeline. These
  can be either specified using the Kubernetes model objects or as dictionaries.

```python
from zenml.integrations.kubernetes.flavors.kubernetes_orchestrator_flavor import KubernetesOrchestratorSettings
from kubernetes.client.models import V1Toleration

kubernetes_settings = KubernetesOrchestratorSettings(
    pod_settings={
        "affinity": {
            "nodeAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "node.kubernetes.io/name",
                                    "operator": "In",
                                    "values": ["my_powerful_node_group"],
                                }
                            ]
                        }
                    ]
                }
            }
        },
        "tolerations": [
            V1Toleration(
                key="node.kubernetes.io/name",
                operator="Equal",
                value="",
                effect="NoSchedule"
            )
        ]
    }
)


@pipeline(
    settings={
        "orchestrator.kubernetes": kubernetes_settings
    }
)


...
```

Check out
the [SDK docs](https://sdkdocs.zenml.io/latest/integration\_code\_docs/integrations-kubernetes/#zenml.integrations.kubernetes.flavors.kubernetes\_orchestrator\_flavor.KubernetesOrchestratorSettings)
for a full list of available attributes and [this docs page](/docs/book/user-guide/advanced-guide/pipelining-features/configure-steps-pipelines.md) for more
information on how to specify settings.

A concrete example of using the Kubernetes orchestrator can be
found [here](https://github.com/zenml-io/zenml/tree/main/examples/kubernetes\_orchestration).

For more information and a full list of configurable attributes of the Kubernetes orchestrator, check out
the [API Docs](https://sdkdocs.zenml.io/latest/integration\_code\_docs/integrations-kubernetes/#zenml.integrations.kubernetes.orchestrators.kubernetes\_orchestrator.KubernetesOrchestrator)
.

#### Enabling CUDA for GPU-backed hardware

Note that if you wish to use this orchestrator to run steps on a GPU, you will need to
follow [the instructions on this page](/docs/book/user-guide/advanced-guide/environment-management/scale-compute-to-the-cloud.md) to ensure 
that it works. It requires adding some extra settings customization and is essential to enable CUDA for the GPU to 
give its full acceleration.

<!-- For scarf -->
<figure><img alt="ZenML Scarf" referrerpolicy="no-referrer-when-downgrade" src="https://static.scarf.sh/a.png?x-pxid=f0b4f458-0a54-4fcd-aa95-d5ee424815bc" /></figure>
