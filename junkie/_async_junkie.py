import asyncio
import inspect
import logging
from collections import OrderedDict
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Union, Tuple, Mapping, Any, Callable, Optional

from junkie._junkie import Junkie, JunkieError, BUILTINS, get_factory_name

LOGGER = logging.getLogger(Junkie.__module__)


class AsyncJunkie(Junkie):
    def __init__(self, instances_and_factories: Mapping[str, Any] = None):
        super().__init__(instances_and_factories)
        self._exit_stack: Optional[AsyncExitStack] = None

    @asynccontextmanager
    async def inject(self, *names_and_factories: Union[str, Callable]):
        LOGGER.debug("inject(%s)", Junkie._LogParams(*names_and_factories))

        async with AsyncExitStack() as self._exit_stack:
            self._instances_by_name = self._instances_by_name_stack.peek().copy()

            with self._instances_by_name_stack.push_temporarily(self._instances_by_name):
                if len(names_and_factories) == 1:
                    yield await self._abuild_instance(names_and_factories[0])
                else:
                    yield await self._abuild_tuple(*names_and_factories)

    async def _abuild_tuple(self, *names_and_factories: Union[str, Callable]) -> Tuple[Any, ...]:
        instances = []

        for name_or_factory in names_and_factories:
            instance = await self._abuild_instance(name_or_factory)
            instances.append(instance)

        return tuple(instances)

    async def _abuild_instance(self, name_or_factory: Union[str, Callable]) -> Any:
        if isinstance(name_or_factory, str):
            return await self._abuild_by_instance_name(name_or_factory)

        elif callable(name_or_factory):
            return await self._abuild_by_factory_function(name_or_factory, None)

        raise JunkieError(
            f"{self._instantiation_stack}" + f'Unknown type "{name_or_factory}" (str, type or Callable expected)'
        )

    async def _abuild_by_instance_name(self, instance_name: str) -> Any:
        if instance_name in self._instances_by_name:
            return self._instances_by_name[instance_name]

        if instance_name in self._context:
            value = self._context[instance_name]

            if callable(value):
                return await self._abuild_by_factory_function(value, instance_name)
            else:
                return value

        raise JunkieError(f"{self._instantiation_stack}" + f'Unable to find "{instance_name}"')

    async def _abuild_by_factory_function(self, factory_function: Callable, instance_name: Union[str, None]) -> Any:
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
            instance = await self._acall_factory_function(factory_function, instance_name)

            if instance_name is not None:
                self._instances_by_name[instance_name] = instance

            return instance

    async def _build_parameters(self, factory_function: Callable) -> tuple:
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
                value = await self._abuild_by_instance_name(instance_name)

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
                value = await self._abuild_by_factory_function(annotation.annotation, instance_name)

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

    async def _acall_factory_function(self, factory_function, instance_name):
        positional_params, args, keyword_params, kwargs = await self._build_parameters(factory_function)

        if LOGGER.isEnabledFor(logging.DEBUG):
            log_params = Junkie._LogParams(*positional_params.keys(), *args, **keyword_params, **kwargs)
            LOGGER.debug("%s = %s(%s)", instance_name or "_", get_factory_name(factory_function), log_params)

        instance = factory_function(*positional_params.values(), *args, **keyword_params, **kwargs)

        # If the factory is async, await it
        if asyncio.iscoroutine(instance):
            instance = await instance

        if hasattr(instance, "__aenter__"):
            if LOGGER.isEnabledFor(logging.DEBUG):
                LOGGER.debug("%s.__aenter__()", instance_name or "_")

            instance = await self._exit_stack.enter_async_context(instance)

        elif hasattr(instance, "__enter__"):
            if LOGGER.isEnabledFor(logging.DEBUG):
                LOGGER.debug("%s.__enter__()", instance_name or "_")

            instance = self._exit_stack.enter_context(instance)

        return instance