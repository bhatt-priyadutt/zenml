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
"""Base Step for ZenML."""
import hashlib
import inspect
import os
from abc import abstractmethod
from collections import defaultdict
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from pydantic import BaseModel, Extra, ValidationError

from zenml.config.source import Source
from zenml.config.step_configurations import (
    PartialArtifactConfiguration,
    PartialStepConfiguration,
    StepConfiguration,
    StepConfigurationUpdate,
)
from zenml.constants import STEP_SOURCE_PARAMETER_NAME
from zenml.exceptions import MissingStepParameterError, StepInterfaceError
from zenml.logger import get_logger
from zenml.materializers.base_materializer import BaseMaterializer
from zenml.materializers.materializer_registry import materializer_registry
from zenml.steps.base_parameters import BaseParameters
from zenml.steps.step_context import StepContext
from zenml.steps.utils import (
    parse_return_type_annotations,
)
from zenml.utils import (
    dict_utils,
    pydantic_utils,
    settings_utils,
    source_code_utils,
    source_utils,
)

if TYPE_CHECKING:
    from zenml.config.base_settings import SettingsOrDict
    from zenml.pipelines.new import Pipeline

    ParametersOrDict = Union["BaseParameters", Dict[str, Any]]
    MaterializerClassOrSource = Union[str, Source, Type["BaseMaterializer"]]
    HookSpecification = Union[str, Source, FunctionType]
    OutputMaterializersSpecification = Union[
        "MaterializerClassOrSource",
        Sequence["MaterializerClassOrSource"],
        Mapping[str, "MaterializerClassOrSource"],
        Mapping[str, Sequence["MaterializerClassOrSource"]],
    ]

logger = get_logger(__name__)


class BaseStepMeta(type):
    """Metaclass for `BaseStep`.

    Makes sure that the entrypoint function has valid parameters and type
    annotations.
    """

    def __new__(
        mcs, name: str, bases: Tuple[Type[Any], ...], dct: Dict[str, Any]
    ) -> "BaseStepMeta":
        """Set up a new class with a qualified spec.

        Args:
            name: The name of the class.
            bases: The base classes of the class.
            dct: The attributes of the class.

        Returns:
            The new class.

        Raises:
            StepInterfaceError: When unable to create the step.
        """
        cls = cast(Type["BaseStep"], super().__new__(mcs, name, bases, dct))
        if name not in {"BaseStep", "_DecoratedStep"}:
            validate_entrypoint_function(cls.entrypoint)

        return cls

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from zenml.pipelines.new import Pipeline

        if not Pipeline.ACTIVE_PIPELINE:
            return super().__call__(*args, **kwargs)

        init_kwargs = {}
        call_kwargs = {}

        # TODO: validate the entrypoint does not define reserved params like
        # "settings" or "extra"
        entrypoint_params = set(inspect.signature(self.entrypoint).parameters)
        entrypoint_params.add("after")
        entrypoint_params.add("id")

        for key, value in kwargs.items():
            if key in entrypoint_params:
                call_kwargs[key] = value
            else:
                init_kwargs[key] = value

        step_instance = super().__call__(**init_kwargs)
        return step_instance(*args, **call_kwargs)


T = TypeVar("T", bound="BaseStep")


class BaseStep(metaclass=BaseStepMeta):
    """Abstract base class for all ZenML steps.

    Attributes:
        name: The name of this step.
        pipeline_parameter_name: The name of the pipeline parameter for which
            this step was passed as an argument.
        enable_cache: A boolean indicating if caching is enabled for this step.
        enable_artifact_metadata: A boolean indicating if artifact metadata
            is enabled for this step.
        enable_artifact_visualization: A boolean indicating if artifact
            visualization is enabled for this step.
    """

    def __init__(
        self,
        *args: Any,
        name: Optional[str] = None,
        enable_cache: Optional[bool] = None,
        enable_artifact_metadata: Optional[bool] = None,
        enable_artifact_visualization: Optional[bool] = None,
        experiment_tracker: Optional[str] = None,
        step_operator: Optional[str] = None,
        parameters: Optional["ParametersOrDict"] = None,
        output_materializers: Optional[
            "OutputMaterializersSpecification"
        ] = None,
        settings: Optional[Mapping[str, "SettingsOrDict"]] = None,
        extra: Optional[Dict[str, Any]] = None,
        on_failure: Optional["HookSpecification"] = None,
        on_success: Optional["HookSpecification"] = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a step.

        Args:
            *args: Positional arguments passed to the step.
            **kwargs: Keyword arguments passed to the step.
        """
        self._upstream_steps: Set[str] = set()
        self.entrypoint_definition = validate_entrypoint_function(
            self.entrypoint
        )

        name = name or self.__class__.__name__

        requires_context = self.entrypoint_definition.context is not None
        if enable_cache is None:
            if requires_context:
                # Using the StepContext inside a step provides access to
                # external resources which might influence the step execution.
                # We therefore disable caching unless it is explicitly enabled
                enable_cache = False
                logger.debug(
                    "Step '%s': Step context required and caching not "
                    "explicitly enabled.",
                    name,
                )

        logger.debug(
            "Step '%s': Caching %s.",
            name,
            "enabled" if enable_cache is not False else "disabled",
        )
        logger.debug(
            "Step '%s': Artifact metadata %s.",
            name,
            "enabled" if enable_artifact_metadata is not False else "disabled",
        )
        logger.debug(
            "Step '%s': Artifact visualization %s.",
            name,
            "enabled"
            if enable_artifact_visualization is not False
            else "disabled",
        )

        self._configuration = PartialStepConfiguration(
            name=name,
            enable_cache=enable_cache,
            enable_artifact_metadata=enable_artifact_metadata,
            enable_artifact_visualization=enable_artifact_visualization,
        )
        self.configure(
            experiment_tracker=experiment_tracker,
            step_operator=step_operator,
            output_materializers=output_materializers,
            parameters=parameters,
            settings=settings,
            extra=extra,
            on_failure=on_failure,
            on_success=on_success,
        )
        self._verify_and_apply_init_params(*args, **kwargs)

    @abstractmethod
    def entrypoint(self, *args: Any, **kwargs: Any) -> Any:
        """Abstract method for core step logic.

        Args:
            *args: Positional arguments passed to the step.
            **kwargs: Keyword arguments passed to the step.

        Returns:
            The output of the step.
        """

    @classmethod
    def load_from_source(cls, source: Union[Source, str]) -> "BaseStep":
        """Loads a step from source.

        Args:
            source: The path to the step source.

        Returns:
            The loaded step.
        """
        step_class: Type[BaseStep] = source_utils.load_and_validate_class(
            source, expected_class=BaseStep
        )
        return step_class()

    @property
    def upstream_steps(self) -> Set[str]:
        """Names of the upstream steps of this step.

        This property will only contain the full set of upstream steps once
        it's parent pipeline `connect(...)` method was called.

        Returns:
            Set of upstream step names.
        """
        return self._upstream_steps

    def after(self, step: "BaseStep") -> None:
        """Adds an upstream step to this step.

        Calling this method makes sure this step only starts running once the
        given step has successfully finished executing.

        **Note**: This can only be called inside the pipeline connect function
        which is decorated with the `@pipeline` decorator. Any calls outside
        this function will be ignored.

        Example:
        The following pipeline will run its steps sequentially in the following
        order: step_2 -> step_1 -> step_3

        ```python
        @pipeline
        def example_pipeline(step_1, step_2, step_3):
            step_1.after(step_2)
            step_3(step_1(), step_2())
        ```

        Args:
            step: A step which should finish executing before this step is
                started.
        """
        self._upstream_steps.add(step)

    @property
    def source_object(self) -> Any:
        """The source object of this step.

        Returns:
            The source object of this step.
        """
        return self.__class__

    @property
    def source_code(self) -> str:
        """The source code of this step.

        Returns:
            The source code of this step.
        """
        return inspect.getsource(self.source_object)

    @property
    def docstring(self) -> Optional[str]:
        """The docstring of this step.

        Returns:
            The docstring of this step.
        """
        return self.__doc__

    @property
    def caching_parameters(self) -> Dict[str, Any]:
        """Caching parameters for this step.

        Returns:
            A dictionary containing the caching parameters
        """
        parameters = {}
        parameters[
            STEP_SOURCE_PARAMETER_NAME
        ] = source_code_utils.get_hashed_source_code(self.source_object)

        for name, output in self.configuration.outputs.items():
            if output.materializer_source:
                key = f"{name}_materializer_source"
                hash_ = hashlib.md5()

                for source in output.materializer_source:
                    materializer_class = source_utils.load(source)
                    code_hash = source_code_utils.get_hashed_source_code(
                        materializer_class
                    )
                    hash_.update(code_hash.encode())

                parameters[key] = hash_.hexdigest()

        return parameters

    def _verify_and_apply_init_params(self, *args: Any, **kwargs: Any) -> None:
        """Verifies the initialization args and kwargs of this step.

        This method makes sure that there is only one parameters object passed
        at initialization and that it was passed using the correct name and
        type specified in the step declaration.

        Args:
            *args: The args passed to the init method of this step.
            **kwargs: The kwargs passed to the init method of this step.

        Raises:
            StepInterfaceError: If there are too many arguments or arguments
                with a wrong name/type.
        """
        maximum_arg_count = 1 if self.entrypoint_definition.params else 0
        arg_count = len(args) + len(kwargs)
        if arg_count > maximum_arg_count:
            raise StepInterfaceError(
                f"Too many arguments ({arg_count}, expected: "
                f"{maximum_arg_count}) passed when creating a "
                f"'{self.name}' step."
            )

        if self.entrypoint_definition.params:
            if args:
                config = args[0]
            elif kwargs:
                key, config = kwargs.popitem()

                if key != self.entrypoint_definition.params.name:
                    raise StepInterfaceError(
                        f"Unknown keyword argument '{key}' when creating a "
                        f"'{self.name}' step, only expected a single "
                        "argument with key "
                        f"'{self.entrypoint_definition.params.name}'."
                    )
            else:
                # This step requires configuration parameters but no parameters
                # object was passed as an argument. The parameters might be
                # set via default values in the parameters class or in a
                # configuration file, so we continue for now and verify
                # that all parameters are set before running the step
                return

            if not isinstance(
                config, self.entrypoint_definition.params.annotation
            ):
                raise StepInterfaceError(
                    f"`{config}` object passed when creating a "
                    f"'{self.name}' step is not a "
                    f"`{self.entrypoint_definition.params.annotation.__name__}` instance."
                )

            self.configure(parameters=config)

    def _parse_call_args(
        self, *args: Any, **kwargs: Any
    ) -> Tuple[
        Dict[str, "StepArtifact"],
        Dict[str, "ExternalArtifact"],
        Dict[str, Any],
    ]:
        signature = get_step_entrypoint_signature(step=self)

        try:
            bound_args = signature.bind_partial(*args, **kwargs)
        except TypeError as e:
            raise StepInterfaceError(
                f"Wrong arguments when calling step '{self.name}': {e}"
            ) from e

        bound_args.apply_defaults()

        artifacts = {}
        external_artifacts = {}
        parameters = {}

        for key, value in bound_args.arguments.items():
            self.entrypoint_definition.validate_input(key=key, input_=value)

            if isinstance(value, StepArtifact):
                artifacts[key] = value
                if key in self.configuration.parameters:
                    logger.warning(
                        "Got duplicate value for step input %s, using value "
                        "provided as artifact.",
                        key,
                    )
            elif isinstance(value, ExternalArtifact):
                external_artifacts[key] = value
                if not value._id:
                    # If the external artifact references a fixed artifact by
                    # ID, caching behaves as expected.
                    logger.warning(
                        "Using an external artifact as step input currently "
                        "invalidates caching for the step and all downstream "
                        "steps. Future releases will introduce hashing of "
                        "artifacts which will improve this behavior."
                    )
            else:
                parameters[key] = value

        return artifacts, external_artifacts, parameters

    def __call__(
        self,
        *args: Any,
        id: Optional[str] = None,
        after: Union[str, Sequence[str], None] = None,
        **kwargs: Any,
    ) -> Any:
        from zenml.pipelines.new.pipeline import Pipeline

        if not Pipeline.ACTIVE_PIPELINE:
            # The step is being called outside of the context of a pipeline,
            # we simply call the entrypoint
            return self.call_entrypoint(*args, **kwargs)

        (
            input_artifacts,
            external_artifacts,
            parameters,
        ) = self._parse_call_args(*args, **kwargs)
        upstream_steps = {
            artifact.invocation_id for artifact in input_artifacts.values()
        }
        if isinstance(after, str):
            upstream_steps.add(after)
        elif isinstance(after, Sequence):
            upstream_steps.union(after)

        invocation_id = Pipeline.ACTIVE_PIPELINE.add_step(
            step=self,
            input_artifacts=input_artifacts,
            external_artifacts=external_artifacts,
            parameters=parameters,
            upstream_steps=upstream_steps,
            custom_id=id,
            allow_suffix=not id,
        )

        outputs = []
        for key, annotation in self.entrypoint_definition.outputs.items():
            output = StepArtifact(
                invocation_id=invocation_id,
                output_name=key,
                annotation=annotation,
                pipeline=Pipeline.ACTIVE_PIPELINE,
            )
            outputs.append(output)

        if len(outputs) == 1:
            return outputs[0]
        else:
            return outputs

    def call_entrypoint(self, *args: Any, **kwargs: Any) -> Any:
        from pydantic.decorator import ValidatedFunction

        validation_func = ValidatedFunction(
            self.entrypoint, config={"arbitrary_types_allowed": True}
        )
        model = validation_func.init_model_instance(*args, **kwargs)

        validated_args = {
            k: v
            for k, v in model._iter()
            if k in model.__fields_set__
            or model.__fields__[k].default_factory
            or model.__fields__[k].default
        }

        return self.entrypoint(**validated_args)

    @property
    def name(self) -> str:
        """The name of the step.

        Returns:
            The name of the step.
        """
        return self.configuration.name

    @property
    def enable_cache(self) -> Optional[bool]:
        """If caching is enabled for the step.

        Returns:
            If caching is enabled for the step.
        """
        return self.configuration.enable_cache

    @property
    def configuration(self) -> PartialStepConfiguration:
        """The configuration of the step.

        Returns:
            The configuration of the step.
        """
        return self._configuration

    def configure(
        self: T,
        name: Optional[str] = None,
        enable_cache: Optional[bool] = None,
        enable_artifact_metadata: Optional[bool] = None,
        enable_artifact_visualization: Optional[bool] = None,
        experiment_tracker: Optional[str] = None,
        step_operator: Optional[str] = None,
        parameters: Optional["ParametersOrDict"] = None,
        output_materializers: Optional[
            "OutputMaterializersSpecification"
        ] = None,
        settings: Optional[Mapping[str, "SettingsOrDict"]] = None,
        extra: Optional[Dict[str, Any]] = None,
        on_failure: Optional["HookSpecification"] = None,
        on_success: Optional["HookSpecification"] = None,
        merge: bool = True,
    ) -> T:
        """Configures the step.

        Configuration merging example:
        * `merge==True`:
            step.configure(extra={"key1": 1})
            step.configure(extra={"key2": 2}, merge=True)
            step.configuration.extra # {"key1": 1, "key2": 2}
        * `merge==False`:
            step.configure(extra={"key1": 1})
            step.configure(extra={"key2": 2}, merge=False)
            step.configuration.extra # {"key2": 2}

        Args:
            name: DEPRECATED: The name of the step.
            enable_cache: If caching should be enabled for this step.
            enable_artifact_metadata: If artifact metadata should be enabled
                for this step.
            enable_artifact_visualization: If artifact visualization should be
                enabled for this step.
            experiment_tracker: The experiment tracker to use for this step.
            step_operator: The step operator to use for this step.
            parameters: Function parameters for this step
            output_materializers: Output materializers for this step. If
                given as a dict, the keys must be a subset of the output names
                of this step. If a single value (type or string) is given, the
                materializer will be used for all outputs.
            settings: settings for this step.
            extra: Extra configurations for this step.
            on_failure: Callback function in event of failure of the step. Can be
                a function with three possible parameters, `StepContext`, `BaseParameters`,
                and `BaseException`, or a source path to a function of the same specifications
                (e.g. `module.my_function`)
            on_success: Callback function in event of failure of the step. Can be
                a function with two possible parameters, `StepContext` and `BaseParameters, or
                a source path to a function of the same specifications
                (e.g. `module.my_function`).
            merge: If `True`, will merge the given dictionary configurations
                like `parameters` and `settings` with existing
                configurations. If `False` the given configurations will
                overwrite all existing ones. See the general description of this
                method for an example.

        Returns:
            The step instance that this method was called on.
        """
        from zenml.hooks.hook_validators import resolve_and_validate_hook

        if name:
            logger.warning("Configuring the name of a step is deprecated.")

        def _resolve_if_necessary(
            value: Union[str, Source, Type[Any]]
        ) -> Source:
            if isinstance(value, str):
                return Source.from_import_path(value)
            elif isinstance(value, Source):
                return value
            else:
                return source_utils.resolve(value)

        def _convert_to_tuple(value: Any) -> Tuple[Source]:
            if isinstance(value, Sequence):
                return tuple(_resolve_if_necessary(v) for v in value)
            else:
                return (_resolve_if_necessary(value),)

        outputs: Dict[str, Dict[str, Source]] = defaultdict(dict)
        allowed_output_names = set(self.entrypoint_definition.outputs)

        if output_materializers:
            if not isinstance(output_materializers, Mapping):
                sources = _convert_to_tuple(output_materializers)
                output_materializers = {
                    output_name: sources
                    for output_name in allowed_output_names
                }

            for output_name, materializer in output_materializers.items():
                sources = _convert_to_tuple(materializer)
                outputs[output_name]["materializer_source"] = sources

        failure_hook_source = None
        if on_failure:
            # string of on_failure hook function to be used for this step
            failure_hook_source = resolve_and_validate_hook(on_failure)

        success_hook_source = None
        if on_success:
            # string of on_success hook function to be used for this step
            success_hook_source = resolve_and_validate_hook(on_success)

        if isinstance(parameters, BaseParameters):
            parameters = parameters.dict()

        values = dict_utils.remove_none_values(
            {
                "enable_cache": enable_cache,
                "enable_artifact_metadata": enable_artifact_metadata,
                "enable_artifact_visualization": enable_artifact_visualization,
                "experiment_tracker": experiment_tracker,
                "step_operator": step_operator,
                "parameters": parameters,
                "settings": settings,
                "outputs": outputs or None,
                "extra": extra,
                "failure_hook_source": failure_hook_source,
                "success_hook_source": success_hook_source,
            }
        )
        config = StepConfigurationUpdate(**values)
        self._apply_configuration(config, merge=merge)
        return self

    def _apply_configuration(
        self,
        config: StepConfigurationUpdate,
        merge: bool = True,
    ) -> None:
        """Applies an update to the step configuration.

        Args:
            config: The configuration update.
            merge: Whether to merge the updates with the existing configuration
                or not. See the `BaseStep.configure(...)` method for a detailed
                explanation.
        """
        self._validate_configuration(config)

        self._configuration = pydantic_utils.update_model(
            self._configuration, update=config, recursive=merge
        )

        logger.debug("Updated step configuration:")
        logger.debug(self._configuration)

    def _validate_configuration(self, config: StepConfigurationUpdate) -> None:
        """Validates a configuration update.

        Args:
            config: The configuration update to validate.
        """
        settings_utils.validate_setting_keys(list(config.settings))
        self._validate_function_parameters(parameters=config.parameters)
        self._validate_outputs(outputs=config.outputs)

    def _validate_function_parameters(
        self, parameters: Dict[str, Any]
    ) -> None:
        """Validates step function parameters.

        Args:
            parameters: The parameters to validate.

        Raises:
            StepInterfaceError: If the step requires no function parameters but
                parameters were configured.
        """
        if not parameters:
            return

        for key, value in parameters.items():
            if key in self.entrypoint_definition.inputs:
                self.entrypoint_definition.validate_input(
                    key=key, input_=value
                )

            elif not self.entrypoint_definition.params:
                raise StepInterfaceError(
                    "Can't set parameter without param class."
                )

    def _validate_outputs(
        self, outputs: Mapping[str, PartialArtifactConfiguration]
    ) -> None:
        """Validates the step output configuration.

        Args:
            outputs: The configured step outputs.

        Raises:
            StepInterfaceError: If an output for a non-existent name is
                configured of an output artifact/materializer source does not
                resolve to the correct class.
        """
        allowed_output_names = set(self.entrypoint_definition.outputs)
        for output_name, output in outputs.items():
            if output_name not in allowed_output_names:
                raise StepInterfaceError(
                    f"Got unexpected materializers for non-existent "
                    f"output '{output_name}' in step '{self.name}'. "
                    f"Only materializers for the outputs "
                    f"{allowed_output_names} of this step can"
                    f" be registered."
                )

            if output.materializer_source:
                for source in output.materializer_source:
                    if not source_utils.validate_source_class(
                        source, expected_class=BaseMaterializer
                    ):
                        raise StepInterfaceError(
                            f"Materializer source `{source}` "
                            f"for output '{output_name}' of step '{self.name}' "
                            "does not resolve to a `BaseMaterializer` subclass."
                        )

    def _validate_inputs(
        self,
        input_artifacts: Dict[str, "StepArtifact"],
        external_artifacts: Dict[str, UUID],
    ) -> None:
        signature = get_step_entrypoint_signature(step=self)
        for key in signature.parameters.keys():
            if (
                key in input_artifacts
                or key in self.configuration.parameters
                or key in external_artifacts
            ):
                continue
            raise StepInterfaceError(f"Missing entrypoint input {key}.")

    def _finalize_configuration(
        self,
        input_artifacts: Dict[str, "StepArtifact"],
        external_artifacts: Dict[str, UUID],
    ) -> StepConfiguration:
        """Finalizes the configuration after the step was called.

        Once the step was called, we know the outputs of previous steps
        and that no additional user configurations will be made. That means
        we can now collect the remaining artifact and materializer types
        as well as check for the completeness of the step function parameters.

        Args:
            input_artifacts: The input artifacts of this step.

        Returns:
            The finalized step configuration.
        """
        outputs: Dict[str, Dict[str, Source]] = defaultdict(dict)

        for (
            output_name,
            output_annotation,
        ) in self.entrypoint_definition.outputs.items():
            output = self._configuration.outputs.get(
                output_name, PartialArtifactConfiguration()
            )

            from pydantic.typing import (
                get_origin,
                is_none_type,
                is_union,
            )

            from zenml.steps.utils import get_args

            if not output.materializer_source:
                if output_annotation is Any:
                    raise StepInterfaceError(
                        "An explicit materializer needs to be specified for "
                        "step outputs with `Any` as type annotation.",
                        url="https://docs.zenml.io/advanced-guide/pipelines/materializers",
                    )

                if is_union(
                    get_origin(output_annotation) or output_annotation
                ):
                    output_types = tuple(
                        type(None)
                        if is_none_type(output_type)
                        else output_type
                        for output_type in get_args(output_annotation)
                    )
                else:
                    output_types = (output_annotation,)

                materializer_source = []

                for output_type in output_types:
                    if materializer_registry.is_registered(output_type):
                        materializer_class = materializer_registry[output_type]
                    else:
                        raise StepInterfaceError(
                            f"Unable to find materializer for output "
                            f"'{output_name}' of type `{output_type}` in step "
                            f"'{self.name}'. Please make sure to either "
                            f"explicitly set a materializer for step outputs "
                            f"using `step.configure(output_materializers=...)` or "
                            f"registering a default materializer for specific "
                            f"types by subclassing `BaseMaterializer` and setting "
                            f"its `ASSOCIATED_TYPES` class variable.",
                            url="https://docs.zenml.io/advanced-guide/pipelines/materializers",
                        )
                    materializer_source.append(
                        source_utils.resolve(materializer_class)
                    )

                outputs[output_name][
                    "materializer_source"
                ] = materializer_source

        parameters = self._finalize_parameters()
        self.configure(parameters=parameters, merge=False)
        self._validate_inputs(
            input_artifacts=input_artifacts,
            external_artifacts=external_artifacts,
        )

        values = dict_utils.remove_none_values({"outputs": outputs or None})
        config = StepConfigurationUpdate(**values)
        self._apply_configuration(config)

        self._configuration = self._configuration.copy(
            update={
                "caching_parameters": self.caching_parameters,
                "external_input_artifacts": external_artifacts,
            }
        )

        complete_configuration = StepConfiguration.parse_obj(
            self._configuration
        )
        return complete_configuration

    def _finalize_parameters(self) -> Dict[str, Any]:
        signature = get_step_entrypoint_signature(step=self)

        params = {}
        for key, value in self.configuration.parameters.items():
            if key not in signature.parameters:
                continue

            annotation = signature.parameters[key].annotation
            if inspect.isclass(annotation) and issubclass(
                annotation, BaseModel
            ):
                # Make sure we have all necessary values to instantiate the
                # pydantic model later
                model = annotation(**value)
                params[key] = model.dict()
            else:
                params[key] = value

        if self.entrypoint_definition.params:
            legacy_params = self._finalize_legacy_parameters()
            params[self.entrypoint_definition.params.name] = legacy_params

        return params

    def _finalize_legacy_parameters(self) -> Dict[str, Any]:
        """Verifies and prepares the config parameters for running this step.

        When the step requires config parameters, this method:
            - checks if config parameters were set via a config object or file
            - tries to set missing config parameters from default values of the
              config class

        Returns:
            Values for the previously unconfigured function parameters.

        Raises:
            MissingStepParameterError: If no value could be found for one or
                more config parameters.
            StepInterfaceError: If the parameter class validation failed.
        """
        if not self.entrypoint_definition.params:
            return {}

        # parameters for the `BaseParameters` class specified in the "new" way
        # by specifying a dict of parameters for the corresponding key
        params_defined_in_new_way = (
            self.configuration.parameters.get(
                self.entrypoint_definition.params.name
            )
            or {}
        )

        values = {}
        missing_keys = []
        for (
            name,
            field,
        ) in self.entrypoint_definition.params.annotation.__fields__.items():
            if name in self.configuration.parameters:
                # a value for this parameter has been set already
                values[name] = self.configuration.parameters[name]
            elif name in params_defined_in_new_way:
                # a value for this parameter has been set in the "new" way
                # already
                values[name] = params_defined_in_new_way[name]
            elif field.required:
                # this field has no default value set and therefore needs
                # to be passed via an initialized config object
                missing_keys.append(name)
            else:
                # use default value from the pydantic config class
                values[name] = field.default

        if missing_keys:
            raise MissingStepParameterError(
                self.name,
                missing_keys,
                self.entrypoint_definition.params.annotation,
            )

        if (
            self.entrypoint_definition.params.annotation.Config.extra
            == Extra.allow
        ):
            # Add all parameters for the config class for backwards
            # compatibility if the config class allows extra attributes
            values.update(self.configuration.parameters)

        try:
            self.entrypoint_definition.params.annotation(**values)
        except ValidationError:
            raise StepInterfaceError("Failed to validate function parameters.")

        return values


def is_json_serializable(obj: Any) -> bool:
    import json

    from pydantic.json import pydantic_encoder

    try:
        json.dumps(obj, default=pydantic_encoder)
        return True
    except TypeError:
        return False


def get_step_entrypoint_signature(
    step: "BaseStep", include_step_context: bool = False
) -> inspect.Signature:
    signature = inspect.signature(step.entrypoint, follow_wrapped=True)

    if include_step_context:
        return signature

    def _is_step_context_param(annotation: Any) -> bool:
        return inspect.isclass(annotation) and issubclass(
            annotation, StepContext
        )

    params_without_step_context = [
        param
        for param in signature.parameters.values()
        if not _is_step_context_param(param.annotation)
    ]

    signature = signature.replace(parameters=params_without_step_context)
    return signature


class StepInvocation:
    def __init__(
        self,
        id: str,
        step: "BaseStep",
        input_artifacts: Dict[str, "StepArtifact"],
        external_artifacts: Dict[str, "ExternalArtifact"],
        parameters: Dict[str, Any],
        upstream_steps: Sequence[str],
        pipeline: "Pipeline",
    ) -> None:
        self.id = id
        self.step = step
        self.input_artifacts = input_artifacts
        self.external_artifacts = external_artifacts
        self.parameters = parameters
        self.invocation_upstream_steps = upstream_steps
        self.pipeline = pipeline

    @property
    def upstream_steps(self) -> Set[str]:
        return self.invocation_upstream_steps.union(
            self._get_and_validate_step_upstream_steps()
        )

    def _get_and_validate_step_upstream_steps(self) -> Set[str]:
        if self.step.upstream_steps:
            # If the step has upstream steps, it can only be part of a single
            # invocation, otherwise it's not clear which invocation should come
            # after the upstream steps
            invocations = {
                invocation
                for invocation in self.pipeline.steps.values()
                if invocation.step is self.step
            }

            if len(invocations) > 1:
                raise RuntimeError(
                    "Setting upstream steps for a step using the `.after(...) "
                    "method is not allowed in combination with calling the "
                    "step multiple times."
                )

        upstream_steps = set()

        for step in self.step.upstream_steps:
            upstream_steps_invocations = {
                invocation.id
                for invocation in self.pipeline.steps.values()
                if invocation.step is step
            }

            if len(upstream_steps_invocations) == 1:
                upstream_steps.add(upstream_steps_invocations.pop())
            elif len(upstream_steps_invocations) > 1:
                raise RuntimeError(
                    "Setting upstream steps for a step using the `.after(...) "
                    "method is not allowed in combination with calling the "
                    "step multiple times."
                )

        return upstream_steps

    def finalize(self) -> StepConfiguration:
        self._get_and_validate_step_upstream_steps()
        self.step.configure(parameters=self.parameters)

        external_artifact_ids = {}
        for key, artifact in self.external_artifacts.items():
            external_artifact_ids[key] = artifact.do_something()

        return self.step._finalize_configuration(
            input_artifacts=self.input_artifacts,
            external_artifacts=external_artifact_ids,
        )


class Artifact:
    @property
    @abstractmethod
    def type(self) -> Any:
        """The data type of the artifact."""


class StepArtifact(Artifact):
    def __init__(
        self,
        invocation_id: str,
        output_name: str,
        annotation: Any,
        pipeline: "Pipeline",
    ) -> None:
        self.invocation_id = invocation_id
        self.output_name = output_name
        self.annotation = annotation
        self.pipeline = pipeline

    @property
    def type(self) -> Any:
        return self.annotation


class ExternalArtifact(Artifact):
    def __init__(
        self,
        value: Any = None,
        id: Optional[UUID] = None,
        materializer: Optional["MaterializerClassOrSource"] = None,
        store_artifact_metadata: bool = True,
        skip_type_checking: bool = False,
    ) -> None:
        if value is not None and id is not None:
            raise ValueError("Only value or ID allowed")
        if value is None and id is None:
            raise ValueError("Either value or ID required")

        self._value = value
        self._id = id
        self._materializer = materializer
        self._store_artifact_metadata = store_artifact_metadata
        self._skip_type_checking = skip_type_checking

    @property
    def type(self) -> Any:
        from zenml.client import Client

        if self._skip_type_checking:
            return Any
        elif self._id:
            response = Client().get_artifact(artifact_id=self._id)
            return source_utils.load(response.data_type)
        else:
            return type(self._value)

    def do_something(self) -> UUID:
        from uuid import uuid4

        from zenml.client import Client
        from zenml.io import fileio
        from zenml.models import ArtifactRequestModel

        artifact_store_id = Client().active_stack.artifact_store.id

        if self._id:
            response = Client().get_artifact(artifact_id=self._id)
            if response.artifact_store_id != artifact_store_id:
                raise RuntimeError("Artifact store mismatch")
        else:
            logger.info("Uploading external artifact.")
            client = Client()
            active_user_id = client.active_user.id
            active_workspace_id = client.active_workspace.id
            artifact_name = f"external_{uuid4()}"
            materializer_class = self._get_materializer()

            uri = os.path.join(
                Client().active_stack.artifact_store.path,
                "external_artifacts",
                artifact_name,
            )
            if fileio.exists(uri):
                raise RuntimeError("Artifact URI already exists")
            fileio.makedirs(uri)

            materializer = materializer_class(uri)
            materializer.save(self._value)

            artifact = ArtifactRequestModel(
                name=artifact_name,
                type=materializer_class.ASSOCIATED_ARTIFACT_TYPE,
                uri=uri,
                materializer=source_utils.resolve(materializer_class),
                data_type=source_utils.resolve(type(self._value)),
                user=active_user_id,
                workspace=active_workspace_id,
                artifact_store_id=artifact_store_id,
            )
            response = Client().zen_store.create_artifact(artifact=artifact)
            # To avoid duplicate uploads, switch to just referencing the
            # uploaded artifact
            self._id = response.id

        return self._id

    def _get_materializer(self) -> Type["BaseMaterializer"]:
        assert self._value is not None

        if inspect.isclass(self._materializer):
            return self._materializer
        elif self._materializer:
            return source_utils.load_and_validate_class(
                self._materializer, expected_class=BaseMaterializer
            )
        else:
            value_type = type(self._value)
            if materializer_registry.is_registered(value_type):
                return materializer_registry[value_type]
            else:
                raise StepInterfaceError(
                    f"Unable to find materializer for type `{value_type}`. Please "
                    "make sure to either explicitly set a materializer for your "
                    "external artifact using "
                    "`ExternalArtifact(value=..., materializer=...)` or "
                    f"register a default materializer for specific "
                    f"types by subclassing `BaseMaterializer` and setting "
                    f"its `ASSOCIATED_TYPES` class variable.",
                    url="https://docs.zenml.io/advanced-guide/pipelines/materializers",
                )


def validate_reserved_arguments(
    signature: inspect.Signature, reserved_arguments: Sequence[str]
):
    for arg in reserved_arguments:
        if arg in signature.parameters:
            raise RuntimeError(f"Reserved argument name {arg}.")


class EntrypointFunctionDefinition(NamedTuple):
    inputs: Dict[str, inspect.Parameter]
    outputs: Dict[str, Any]
    context: Optional[inspect.Parameter]
    params: Optional[inspect.Parameter]

    def validate_input(
        self,
        key: str,
        input_: Union["Artifact", Any],
    ) -> None:
        from zenml.materializers import UnmaterializedArtifact

        if key not in self.inputs:
            raise KeyError(f"No input for key {key}.")

        parameter = self.inputs[key]

        if isinstance(input_, Artifact):
            pass
            # TODO: If we want to do some type validation here, it won't support
            # type coercion
            # if parameter.annotation is not UnmaterializedArtifact:
            #     self._validate_input_type(
            #         parameter=parameter, annotation=input_.type
            #     )
        else:
            # Not an artifact -> This is a parameter
            if parameter.annotation is UnmaterializedArtifact:
                raise RuntimeError(
                    "Passing parameter for input of type `UnmaterializedArtifact` "
                    "is not allowed."
                )

            self._validate_input_value(parameter=parameter, value=input_)

            if not is_json_serializable(input_):
                raise StepInterfaceError(
                    f"Argument type (`{type(input_)}`) for argument "
                    f"'{key}' is not JSON "
                    "serializable."
                )

    def _validate_input_value(
        self, parameter: inspect.Parameter, value: Any
    ) -> None:
        from pydantic import BaseConfig, ValidationError, create_model

        class ModelConfig(BaseConfig):
            arbitrary_types_allowed = False

        # Create a pydantic model with just a single required field with the
        # type annotation of the parameter to verify the input type including
        # pydantics type coercion
        validation_model_class = create_model(
            "input_validation_model",
            __config__=ModelConfig,
            value=(parameter.annotation, ...),
        )

        try:
            validation_model_class(value=value)
        except ValidationError as e:
            raise RuntimeError("Input validation failed.") from e

    def _validate_input_type(
        self, parameter: inspect.Parameter, annotation: Any
    ) -> None:
        from pydantic.typing import get_origin, is_union

        from zenml.steps.utils import get_args

        def _get_allowed_types(annotation) -> Tuple:
            origin = get_origin(annotation) or annotation
            if is_union(origin):
                allowed_types = get_args(annotation)
            elif inspect.isclass(annotation) and issubclass(
                annotation, BaseModel
            ):
                if annotation.__custom_root_type__:
                    allowed_types = (annotation,) + _get_allowed_types(
                        annotation.__fields__["__root__"].outer_type_
                    )
                else:
                    allowed_types = (annotation, dict)
            else:
                allowed_types = (origin,)

            return allowed_types

        allowed_types = _get_allowed_types(annotation=parameter.annotation)
        input_types = _get_allowed_types(annotation=annotation)

        if Any in input_types or Any in allowed_types:
            # Skip type checks for `Any` annotations
            return

        for type_ in input_types:
            if not issubclass(type_, allowed_types):
                raise StepInterfaceError(
                    f"Wrong input type (`{annotation}`) for argument "
                    f"'{parameter.name}'. The argument "
                    f"should be of type `{parameter.annotation}`."
                )


def validate_entrypoint_function(
    func: Callable[..., Any], reserved_arguments: Sequence[str] = ()
) -> EntrypointFunctionDefinition:
    signature = inspect.signature(func, follow_wrapped=True)
    validate_reserved_arguments(
        signature=signature, reserved_arguments=reserved_arguments
    )

    inputs = {}
    context: Optional[inspect.Parameter] = None
    params: Optional[inspect.Parameter] = None

    for key, parameter in signature.parameters.items():
        if parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}:
            raise StepInterfaceError(
                f"Variable args or kwargs not allowed for function {func.__name__}."
            )

        annotation = parameter.annotation
        if annotation is parameter.empty:
            raise StepInterfaceError(
                f"Missing type annotation for argument '{key}'. Please make "
                "sure to include type annotations for all your step inputs "
                f"and outputs."
            )

        if inspect.isclass(annotation) and issubclass(
            annotation, BaseParameters
        ):
            if params is not None:
                raise StepInterfaceError(
                    f"Found multiple parameter arguments "
                    f"('{params.name}' and '{key}') "
                    f"for function {func.__name__}."
                )
            params = parameter

        elif inspect.isclass(annotation) and issubclass(
            annotation, StepContext
        ):
            if context is not None:
                raise StepInterfaceError(
                    f"Found multiple context arguments "
                    f"('{context.name}' and '{key}') "
                    f"for function {func.__name__}."
                )
            context = parameter
        else:
            inputs[key] = parameter

    if signature.return_annotation is signature.empty:
        raise StepInterfaceError(
            f"Missing return type annotation for function {func.__name__}."
        )

    outputs = parse_return_type_annotations(
        return_annotation=signature.return_annotation
    )

    return EntrypointFunctionDefinition(
        inputs=inputs, outputs=outputs, context=context, params=params
    )
