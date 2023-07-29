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

# How many seconds to wait before uploading logs to the artifact store
LOGS_HANDLER_INTERVAL_SECONDS: int = 5

# How many messages to buffer before uploading logs to the artifact store
LOGS_HANDLER_MAX_MESSAGES: int = 100

# Name of the ZenML step logger
STEP_STDOUT_LOGGER_NAME = "_step_stdout_logger"
STEP_STDERR_LOGGER_NAME = "_step_stderr_logger"
