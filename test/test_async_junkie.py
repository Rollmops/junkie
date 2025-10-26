from contextlib import asynccontextmanager, contextmanager

import pytest

from junkie import AsyncJunkie, JunkieError


class TestAsyncJunkie:
    @pytest.mark.asyncio
    async def test_resolve_instance_by_name(self):
        context = {"text": "abc"}

        async with AsyncJunkie(context).inject("text") as instance:
            assert instance == "abc"

    @pytest.mark.asyncio
    async def test_resolve_instance_with_factory_by_name(self):
        context = {"text": lambda: "abc"}

        async with AsyncJunkie(context).inject("text") as instance:
            assert instance == "abc"

    @pytest.mark.asyncio
    async def test_resolve_instance_with_async_factory_by_name(self):
        async def async_factory():
            return "abc"

        context = {"text": async_factory}

        async with AsyncJunkie(context).inject("text") as instance:
            assert instance == "abc"

    @pytest.mark.asyncio
    async def test_raise_exception_if_instance_name_is_unknown(self):
        with pytest.raises(Exception) as exception_context:
            async with AsyncJunkie().inject("instance_name"):
                pass

        assert 'Unable to find "instance_name"' in str(exception_context.value)

    @pytest.mark.asyncio
    async def test_resolve_instance_with_factory_by_type(self):
        class AppClass:
            def __init__(self, text: str):
                self.text = text

        context = {"text": "abc"}

        async with AsyncJunkie(context).inject(AppClass) as instance:
            assert instance.text == "abc"

    @pytest.mark.asyncio
    async def test_resolve_instance_with_async_factory_by_type(self):
        class AppClass:
            def __init__(self, text: str):
                self.text = text

        async def async_text():
            return "abc"

        context = {"text": async_text}

        async with AsyncJunkie(context).inject(AppClass) as instance:
            assert instance.text == "abc"

    @pytest.mark.asyncio
    async def test_resolve_instance_with_factory_using_two_instances(self):
        context = {
            "prefix": "abc",
            "suffix": "def",
            "text": lambda prefix, suffix: prefix + " " + suffix
        }

        async with AsyncJunkie(context).inject("text") as text:
            assert text == "abc def"

    @pytest.mark.asyncio
    async def test_resolve_instance_parameters(self):
        context = {
            "prefix": "abc",
            "suffix": "def",
            "text": lambda prefix, suffix: prefix + " " + suffix
        }

        async with AsyncJunkie(context).inject("prefix", "suffix", "text") as (my_prefix, my_suffix, text):
            assert (my_prefix, my_suffix, text) == ("abc", "def", "abc def")

    @pytest.mark.asyncio
    async def test_resolve_None_as_parameter(self):
        class Class:
            def __init__(self, empty):
                self.empty = empty

        context = {"empty": None, "class": Class}

        async with AsyncJunkie(context).inject("empty", "class") as (empty_value, class_value):
            assert empty_value is None
            assert class_value.empty is None

    @pytest.mark.asyncio
    async def test_default_argument_usage(self):
        class MyClassWithDefaultArguments:
            def __init__(self, argument: str, default_argument: int = 10, default_argument2: str = None):
                self.argument = argument
                self.default_argument = default_argument
                self.default_argument2 = default_argument2 or "Hello"

        context = {"argument": "value"}

        async with AsyncJunkie(context).inject(MyClassWithDefaultArguments) as instance:
            assert instance.argument == "value"
            assert instance.default_argument == 10
            assert instance.default_argument2 == "Hello"

    @pytest.mark.asyncio
    async def test_partial_default_arguments_usage(self):
        class MyClassWithDefaultArguments:
            def __init__(self, argument: str, default_argument: int = 10, default_argument2: str = None):
                self.argument = argument
                self.default_argument = default_argument
                self.default_argument2 = default_argument2 or "Hello"

        context = {"argument": "value", "default_argument2": "set from context"}

        async with AsyncJunkie(context).inject(MyClassWithDefaultArguments) as instance:
            assert instance.argument == "value"
            assert instance.default_argument == 10
            assert instance.default_argument2 == "set from context"

    @pytest.mark.asyncio
    async def test_empty_args_usage(self):
        class MyClassWithKwargs:
            def __init__(self, *args):
                self.args = args

        async with AsyncJunkie().inject(MyClassWithKwargs) as instance:
            assert instance.args == ()

    @pytest.mark.asyncio
    async def test_args_usage_with_tuple(self):
        class MyClassWithKwargs:
            def __init__(self, *my_tuple):
                self.my_tuple = my_tuple

        context = {"my_tuple": (1, 2, 3)}

        async with AsyncJunkie(context).inject(MyClassWithKwargs) as instance:
            assert instance.my_tuple == (1, 2, 3)

    @pytest.mark.asyncio
    async def test_args_usage_with_list_as_tuple_input(self):
        class MyClassWithKwargs:
            def __init__(self, *my_tuple):
                self.my_tuple = my_tuple

        context = {"my_tuple": [1, 2, 3]}

        async with AsyncJunkie(context).inject(MyClassWithKwargs) as instance:
            assert instance.my_tuple == (1, 2, 3)

    @pytest.mark.asyncio
    async def test_args_usage_with_factory_function(self):
        class MyClassWithKwargs:
            def __init__(self, *my_tuple):
                self.my_tuple = my_tuple

        context = {"my_tuple": lambda: (1, 2, 3)}

        async with AsyncJunkie(context).inject(MyClassWithKwargs) as instance:
            assert instance.my_tuple == (1, 2, 3)

    @pytest.mark.asyncio
    async def test_empty_kwargs_usage(self):
        class MyClassWithKwargs:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        async with AsyncJunkie().inject(MyClassWithKwargs) as instance:
            assert instance.kwargs == {}

    @pytest.mark.asyncio
    async def test_kwargs_usage_with_dictionary(self):
        class MyClassWithKwargs:
            def __init__(self, **my_vars):
                self.my_vars = my_vars

        context = {"my_vars": {"a": "a"}}

        async with AsyncJunkie(context).inject(MyClassWithKwargs) as instance:
            assert instance.my_vars == {"a": "a"}

    @pytest.mark.asyncio
    async def test_kwargs_usage_with_factory_function(self):
        class MyClassWithKwargs:
            def __init__(self, **my_vars):
                self.my_vars = my_vars

        context = {"my_vars": lambda: {"a": "a"}}

        async with AsyncJunkie(context).inject(MyClassWithKwargs) as instance:
            assert instance.my_vars == {"a": "a"}

    @pytest.mark.asyncio
    async def test_async_context_manager_aenter_and_aexit(self):
        class Class:
            def __init__(self, message_service, database):
                self.message_service = message_service
                self.database = database

        class MessageService:
            def __init__(self, logger):
                self.logger = logger

            async def __aenter__(self):
                self.logger.append("connect")
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                self.logger.append("disconnect")

        @asynccontextmanager
        async def create_database(logger):
            logger.append("open")
            yield "DB"
            logger.append("close")

        test_logger = []
        context = {
            "logger": test_logger,
            "message_service": MessageService,
            "database": create_database,
        }

        async with AsyncJunkie(context).inject(Class) as instance:
            assert isinstance(instance.message_service, MessageService)
            assert test_logger == ["connect", "open"]

        assert test_logger == ["connect", "open", "close", "disconnect"]

    @pytest.mark.asyncio
    async def test_async_context_manager_enter_and_exit(self):
        class MessageService:
            def __init__(self, logger):
                self.logger = logger

            def __enter__(self):
                self.logger.append("connect")
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.logger.append("disconnect")

        class Class:
            def __init__(self, message_service, database):
                self.message_service = message_service
                self.database = database

        @contextmanager
        def create_database(logger):
            logger.append("open")
            yield "DB"
            logger.append("close")

        test_logger = []
        context = {
            "logger": test_logger,
            "message_service": MessageService,
            "database": create_database,
        }

        async with AsyncJunkie(context).inject(Class) as instance:
            assert isinstance(instance.message_service, MessageService)
            assert test_logger == ["connect", "open"]

        assert test_logger == ["connect", "open", "close", "disconnect"]

    @pytest.mark.asyncio
    async def test_auto_inject(self):
        class A:
            pass

        class B:
            def __init__(self, a: A):
                self.a = a

        class C:
            def __init__(self, b: B):
                self.b = b

        async with AsyncJunkie().inject(C) as c_instance:
            assert isinstance(c_instance, C)
            assert isinstance(c_instance.b, B)
            assert isinstance(c_instance.b.a, A)

    @pytest.mark.asyncio
    async def test_no_auto_inject_for_default_arguments(self):
        class A:
            pass

        class B:
            def __init__(self, a: A = None):
                self.a = a

        async with AsyncJunkie().inject(B) as b_instance:
            assert isinstance(b_instance, B)
            assert b_instance.a is None

    @pytest.mark.asyncio
    async def test_auto_inject_prioritize_named_from_context(self):
        class A:
            pass

        class B:
            def __init__(self, a: A):
                self.a = a

        context = {"a": "from context"}

        async with AsyncJunkie(context).inject(B) as b:
            assert isinstance(b, B)
            assert b.a == "from context"

    @pytest.mark.asyncio
    async def test_no_create_for_builtins(self):
        with pytest.raises(JunkieError):
            async with AsyncJunkie().inject(dict):
                pass

    @pytest.mark.asyncio
    async def test_no_auto_inject_for_builtins(self):
        class B:
            def __init__(self, a: str):
                self.a = a

        with pytest.raises(JunkieError) as error:
            async with AsyncJunkie().inject(B):
                pass

        assert 'Mapping for "a" of builtin type "str" is missing' in str(error.value)

    @pytest.mark.asyncio
    async def test_object_is_persisted(self):
        class A:
            pass

        context = {
            "a": A,
        }

        _junkie = AsyncJunkie(context)
        async with _junkie.inject("a") as a1:
            async with _junkie.inject("a") as a2:
                async with _junkie.inject("a") as a3:
                    assert a1 is a2
                    assert a1 is a3

    @pytest.mark.asyncio
    async def test_resolve_instance_per_context_key(self):
        class A:
            pass

        context = {
            "a": A,
            "b": A,
        }

        _junkie = AsyncJunkie(context)
        async with _junkie.inject("a", "b") as (a1, b1):
            async with _junkie.inject("a", "b") as (a2, b2):
                assert a1 is not b1
                assert a2 is not b2
                assert a1 is a2
                assert b1 is b2

    @pytest.mark.asyncio
    async def test_type_as_key_in_mapping_is_ignored(self):
        class A:
            pass

        context = {
            A: "a",
        }

        # noinspection PyTypeChecker
        async with AsyncJunkie(context).inject(A) as a:
            assert isinstance(a, A)

    @pytest.mark.asyncio
    async def test_auto_inject_same_instance_by_name(self):
        class A:
            pass

        class A1:
            pass

        class B:
            def __init__(self, a: A):
                self.a = a

        class C:
            def __init__(self, a: A1):
                self.a = a

        async with AsyncJunkie().inject(B, C) as (b, c):
            assert b.a is c.a
            assert isinstance(b.a, A)

        async with AsyncJunkie().inject(C, B) as (c, b):
            assert b.a is c.a
            assert isinstance(b.a, A1)

    @pytest.mark.asyncio
    async def test_inject_junkie_reference(self):
        my_junkie = AsyncJunkie()

        async with my_junkie.inject("_junkie") as injected_junkie:
            assert injected_junkie is my_junkie
