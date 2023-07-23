#  Copyright (c) ZenML GmbH 2023. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""AzureMLPipelines orchestrator flavor."""

from typing import TYPE_CHECKING, Optional, Type, Any
from zenml.constants import KUBERNETES_CLUSTER_RESOURCE_TYPE
from zenml.orchestrators import BaseOrchestratorConfig, BaseOrchestratorFlavor
from zenml.config.base_settings import BaseSettings
from zenml.logger import get_logger

logger = get_logger(__name__)


AZURE_ML_PIPELINES_ORCHESTRATOR_FLAVOR = "azure_ml_pipelines"


class AzureMLPipelinesOrchestratorSettings(BaseSettings):
    """Settings for the AzureMLPipelines orchestrator.

    Attributes:
        pod_settings: Pod settings to apply.
    """



class AzureMLPipelinesOrchestratorConfig(  # type: ignore[misc] # https://github.com/pydantic/pydantic/issues/4173
    BaseOrchestratorConfig, AzureMLPipelinesOrchestratorSettings
):
    """Configuration for the AzureMLPipelines orchestrator.

    Attributes:
        kubernetes_context: Name of a kubernetes context to run
            pipelines in. If the stack component is linked to a Kubernetes
            service connector, this field is ignored. Otherwise, it is
            mandatory.
        kubernetes_namespace: Name of the kubernetes namespace in which the
            pods that run the pipeline steps should be running.
        local: If `True`, the orchestrator will assume it is connected to a
            local kubernetes cluster and will perform additional validations and
            operations to allow using the orchestrator in combination with other
            local stack components that store data in the local filesystem
            (i.e. it will mount the local stores directory into the pipeline
            containers).
        skip_local_validations: If `True`, the local validations will be
            skipped.
    """

    kubernetes_context: Optional[str] = None
    kubernetes_namespace: str = "zenml"
    local: bool = False
    skip_local_validations: bool = False

    @property
    def is_remote(self) -> bool:
        """Checks if this stack component is running remotely.

        This designation is used to determine if the stack component can be
        used with a local ZenML database or if it requires a remote ZenML
        server.

        Returns:
            True if this config is for a remote component, False otherwise.
        """
        return not self.local

    @property
    def is_local(self) -> bool:
        """Checks if this stack component is running locally.

        This designation is used to determine if the stack component can be
        shared with other users or if it is only usable on the local host.

        Returns:
            True if this config is for a local component, False otherwise.
        """
        return self.local


class AzureMLPipelinesOrchestratorFlavor(BaseOrchestratorFlavor):
    """Flavor for the AzureMLPipelines orchestrator."""

    @property
    def name(self) -> str:
        """Name of the orchestrator flavor.

        Returns:
            Name of the orchestrator flavor.
        """
        return AZURE_ML_PIPELINES_ORCHESTRATOR_FLAVOR

    @property
    def docs_url(self) -> Optional[str]:
        """A url to point at docs explaining this flavor.

        Returns:
            A flavor docs url.
        """
        return self.generate_default_docs_url()

    @property
    def sdk_docs_url(self) -> Optional[str]:
        """A url to point at SDK docs explaining this flavor.

        Returns:
            A flavor SDK docs url.
        """
        return self.generate_default_sdk_docs_url()

    @property
    def logo_url(self) -> str:
        """A url to represent the flavor in the dashboard.

        Returns:
            The flavor logo.
        """
        return "https://public-flavor-logos.s3.eu-central-1.amazonaws.com/orchestrator/azure_ml_pipelines.png"

    @property
    def config_class(self) -> Type[AzureMLPipelinesOrchestratorConfig]:
        """Returns `AzureMLPipelinesOrchestratorConfig` config class.

        Returns:
                The config class.
        """
        return AzureMLPipelinesOrchestratorConfig

    @property
    def implementation_class(self) -> Type[Any]:
        """Implementation class for this flavor.

        Returns:
            Implementation class for this flavor.
        """
        from orchestrator.azure_ml_pipelines_orchestrator import AzureMLPipelinesOrchestrator

        return AzureMLPipelinesOrchestrator
