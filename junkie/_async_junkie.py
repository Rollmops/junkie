import contextlib
import inspect
import logging
from collections import OrderedDict
from typing import Union, Callable, Any, Tuple

from junkie import Junkie, JunkieError
from junkie._junkie import BUILTINS, get_factory_name

LOGGER = logging.getLogger(__name__)

class AsyncJunkie(Junkie):

    @contextlib.asynccontextmanager
    async def inject(self, *names_and_factories: Union[str, Callable]) -> Union[Any, Tuple[Any]]:
        LOGGER.debug("inject(%s)", Junkie._LogParams(*names_and_factories))

        async with contextlib.AsyncExitStack() as self._exit_stack:
            self._instances_by_name = self._instances_by_name_stack.peek().copy()

            with self._instances_by_name_stack.push_temporarily(self._instances_by_name):
                if len(names_and_factories) == 1:
                    yield await self._build_instance(names_and_factories[0])
                else:
                    yield await self._build_tuple(*names_and_factories)

    async def _build_tuple(self, *names_and_factories: Union[str, Callable]) -> Tuple[Any, ...]:
        instances = []

        for name_or_factory in names_and_factories:
            instance = await self._build_instance(name_or_factory)
            instances.append(instance)

        return tuple(instances)

    async def _build_instance(self, name_or_factory: Union[str, Callable]) -> Any:
        if isinstance(name_or_factory, str):
            return await self._build_by_instance_name(name_or_factory)

        elif callable(name_or_factory):
            return await self._build_by_factory_function(name_or_factory, None)

        raise JunkieError(
            f"{self._instantiation_stack}" + f'Unknown type "{name_or_factory}" (str, type or Callable expected)'
        )

    async def _build_by_instance_name(self, instance_name: str) -> Any:
        if instance_name in self._instances_by_name:
            return await self._instances_by_name[instance_name]

        if instance_name in self._context:
            value = self._context[instance_name]

            if callable(value):
                return await self._build_by_factory_function(value, instance_name)
            else:
                return value

        raise JunkieError(f"{self._instantiation_stack}" + f'Unable to find "{instance_name}"')

    async def _build_by_factory_function(self, factory_function: Callable, instance_name: Union[str, None]) -> Any:
        if factory_function in BUILTINS:
            raise JunkieError(
                f"{self._instantiation_stack}"
                + f'Mapping for "{instance_name}" of builtin type "{get_factory_name(factory_function)}" is missing'
            )

        if factory_function in self._instantiation_stack:
            raise JunkieError(
                f"{self._instantiation_stack}"
                + f'Dependency cycle detected with "{get_factory_name(factory_function)}()"'
            )

        with self._instantiation_stack.push_temporarily(factory_function):
            instance = await self._call_factory_function(factory_function, instance_name)

            if instance_name is not None:
                self._instances_by_name[instance_name] = instance

            return instance

    async def _call_factory_function(self, factory_function, instance_name):
        positional_params, args, keyword_params, kwargs = await self._build_parameters(factory_function)

        if LOGGER.isEnabledFor(logging.DEBUG):
            log_params = Junkie._LogParams(*positional_params.keys(), *args, **keyword_params, **kwargs)
            LOGGER.debug("%s = %s(%s)", instance_name or "_", get_factory_name(factory_function), log_params)

        instance = factory_function(*positional_params.values(), *args, **keyword_params, **kwargs)

        if hasattr(instance, "__aenter__"):
            if LOGGER.isEnabledFor(logging.DEBUG):
                LOGGER.debug("%s.__aenter__()", instance_name or "_")
                self._exit_stack.push(lambda *exception_details: LOGGER.debug("%s.__aexit__()", instance_name or "_"))

            instance = await self._exit_stack.enter_async_context(instance)

        return instance

    async def _build_parameters(self, factory_function: Callable) -> tuple[OrderedDict, tuple, OrderedDict, dict]:
        positional_params = OrderedDict()
        args = ()
        keyword_params = OrderedDict()
        kwargs = {}
        positional_params_finished = False

        try:
            signature = inspect.signature(factory_function)
        except Exception as e:
            raise JunkieError(
                f"{self._instantiation_stack}"
                + f'Unable to inspect signature for "{get_factory_name(factory_function)}()"'
            ) from e

        for instance_name, annotation in signature.parameters.items():
            if instance_name in self._instances_by_name or instance_name in self._context:
                value = await self._build_by_instance_name(instance_name)

            # *args
            elif annotation.kind is inspect.Parameter.VAR_POSITIONAL:
                continue

            # **kwargs
            elif annotation.kind is inspect.Parameter.VAR_KEYWORD:
                continue

            # arg="value"
            elif annotation.default is not inspect.Parameter.empty:
                positional_params_finished = True
                continue

            elif isinstance(annotation.annotation, Callable) and annotation.annotation != inspect.Parameter.empty:
                value = await self._build_by_factory_function(annotation.annotation, instance_name)

            else:
                raise JunkieError(
                    f"{self._instantiation_stack}"
                    + f'Unable to find "{instance_name}" for "{get_factory_name(factory_function)}()"'
                )

            if annotation.kind is inspect.Parameter.POSITIONAL_ONLY:
                positional_params[instance_name] = value

            elif annotation.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD:
                if positional_params_finished:
                    keyword_params[instance_name] = value
                else:
                    positional_params[instance_name] = value

            elif annotation.kind is inspect.Parameter.VAR_POSITIONAL:
                args = value

            elif annotation.kind is inspect.Parameter.KEYWORD_ONLY:
                keyword_params[instance_name] = value

            elif annotation.kind is inspect.Parameter.VAR_KEYWORD:
                kwargs = value

            else:
                raise NotImplementedError(f'Unknown parameter type "{annotation.kind}"')

        return positional_params, args, keyword_params, kwargs

    class _LogParams:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __str__(self):
            arg_params = list(map(str, self.args))
            kwarg_params = list(map(str, [f"{key}={repr(value)}" for key, value in self.kwargs.items()]))
            return ", ".join(arg_params + kwarg_params)

    class _Stack:
        def __init__(self):
            self._stack = []

        def push(self, item):
            self._stack.append(item)

        def pop(self):
            return self._stack.pop()

        def peek(self):
            return self._stack[-1]

        @contextlib.contextmanager
        def push_temporarily(self, item):
            self.push(item)
            try:
                yield self
            finally:
                self.pop()

        def __len__(self):
            return self._stack.__len__()

        def __contains__(self, item):
            return item in self._stack

    class _InstantiationStack(_Stack):
        def __str__(self):
            if len(self._stack) == 0:
                return ""

            return "".join([
                f'\n{idx * " "}-> {get_factory_name(factory)}() at {self._get_source_info(factory)}'
                for idx, factory in enumerate(self._stack)
            ]) + "\n"

        @staticmethod
        def _get_source_info(factory: Callable) -> str:
            while hasattr(factory, "__wrapped__"):
                factory = factory.__wrapped__
            try:
                return f'"{inspect.getsourcefile(factory)}:{inspect.getsourcelines(factory)[1]}"'
            except:
                return "unknown source"