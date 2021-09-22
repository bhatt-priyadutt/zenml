import inspect
from abc import abstractmethod

from zenml.annotations.artifact_annotations import Input
from zenml.annotations.step_annotations import Step
from zenml.utils.exceptions import PipelineInterfaceError


class BasePipelineMeta(type):
    """ """

    def __new__(mcs, name, bases, dct):
        cls = super().__new__(mcs, name, bases, dct)

        cls.STEP_SPEC = dict()
        cls.INPUT_SPEC = dict()

        connect_spec = inspect.getfullargspec(cls.connect)
        connect_args = connect_spec.args

        if connect_args and connect_args[0] == "self":
            connect_args.pop(0)

        for arg in connect_args:
            arg_type = connect_spec.annotations.get(arg, None)
            if isinstance(arg_type, Step):
                cls.STEP_SPEC.update({arg: arg_type.type})
            elif isinstance(arg_type, Input):
                cls.INPUT_SPEC.update({arg: arg_type.type})
            else:
                raise PipelineInterfaceError("")  # TODO: fill message
        return cls


class BasePipeline(metaclass=BasePipelineMeta):
    """ """

    def __init__(self, *args, **kwargs):
        self.__steps = dict()
        self.__inputs = dict()

        if args:
            raise PipelineInterfaceError(
                "You can only use keyword arguments while you are creating an"
                "instance of a pipeline."
            )

        for k, v in kwargs.items():
            if k in self.STEP_SPEC:
                self.__steps.update({k: v})
            elif k in self.INPUT_SPEC:
                self.__inputs.update({k: v})
            else:
                raise PipelineInterfaceError(
                    f"The argument {k} is an unknown argument. Needs to be "
                    f"one of either {self.INPUT_SPEC.keys()} or "
                    f"{self.STEP_SPEC.keys()}"
                )

    @abstractmethod
    def connect(self, *args, **kwargs):
        """ """

    def run(self, **pipeline_args):
        """ """
        # DEBUG # TODO: to be removed
        from zenml.providers.local_provider import LocalProvider
        provider = LocalProvider()

        provider.orchestrator.run(self, **pipeline_args)
