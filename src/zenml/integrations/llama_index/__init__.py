#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
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
"""Initialization of the Llama Index integration."""
from zenml.integrations.integration import Integration

from zenml.logger import get_logger
from zenml.integrations.constants import LLAMA_INDEX
from zenml.integrations.integration import Integration

logger = get_logger(__name__)


class LlamaIndexIntegration(Integration):
    """Definition of Llama Index integration for ZenML."""

    NAME = LLAMA_INDEX
    REQUIREMENTS = ["llama_index>=0.4.28"]

    @classmethod
    def activate(cls) -> None:
        """Activates the integration."""
        from zenml.integrations.llama_index import materializers  # noqa


LlamaIndexIntegration.check_installation()
