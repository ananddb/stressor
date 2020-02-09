# -*- coding: utf-8 -*-
# (c) 2020 Martin Wendt and contributors; see https://github.com/mar10/stressor
# Licensed under the MIT license: https://www.opensource.org/licenses/mit-license.php
"""
"""
import pytest

from stressor.util import (
    assert_always,
    check_arg,
    format_elap,
    parse_args_from_str,
    PathStack,
    shorten_string,
)


class TestBasics:
    def test_assert(self):
        assert_always(1)
        assert_always(1, "test")
        with pytest.raises(AssertionError):
            assert_always(0)
        with pytest.raises(AssertionError, match=".*foobar.*"):
            assert_always(0, "foobar")

    def test_check_arg(self):
        def foo(name, amount, options=None):
            check_arg(name, str)
            check_arg(amount, (int, float), amount > 0)
            check_arg(options, dict, or_none=True)
            return name

        assert foo("x", 10) == "x"
        assert foo("x", 10, {1: 2}) == "x"
        with pytest.raises(TypeError, match=".*but got <class 'int'>.*"):
            foo("x", 10, 42)
        with pytest.raises(ValueError, match=".*Invalid argument value.*"):
            foo("x", -10)
        return

    def test_pathstack(self):
        path = PathStack()
        assert str(path) == "/"
        path.push("root")
        assert str(path) == "/root"
        with path.enter("sub1"):
            assert str(path) == "/root/sub1"
        assert str(path) == "/root"
        assert path.pop() == "root"
        with pytest.raises(IndexError):
            path.pop()

    def test_shorten_string(self):
        s = (
            "Do you see any Teletubbies in here?"
            "Do you see a slender plastic tag clipped to my shirt with my name printed on it?"
        )
        assert shorten_string(None, 10) is None
        assert len(shorten_string(s, 20)) == 20
        assert len(shorten_string(s, 20, min_tail_chars=7)) == 20
        assert shorten_string(s, 20) == "Do you see any [...]"
        assert shorten_string(s, 20, min_tail_chars=7) == "Do you s[...] on it?"

    def test_format_elap(self):
        assert format_elap(1.23456) == "1.2 sec"
        assert format_elap(1.23456, high_prec=True) == "1.235 sec"
        assert format_elap(3677) == "1:01:17 hrs"
        assert format_elap(367) == "6:07 min"
        assert format_elap(367, high_prec=True) == "6:07.00 min"
        assert format_elap(12.34, count=10) == "12.3 sec, 0.8 items/sec"

    def test_parse_args_from_str(self):
        arg_def = (
            ("min", float),
            ("max", float, None),
        )
        res = parse_args_from_str("1.23", arg_def)
        assert res == {"min": 1.23, "max": None}

        res = parse_args_from_str("1.23, 42", arg_def)
        assert res == {"min": 1.23, "max": 42.0}

        with pytest.raises(TypeError):
            parse_args_from_str(None, arg_def)

        with pytest.raises(ValueError, match=".*Extra arg.*"):
            parse_args_from_str("1.23, 42, 32", arg_def)

        with pytest.raises(ValueError, match=".*convert string to float: 'foo'.*"):
            parse_args_from_str("1.23, foo", arg_def)

        arg_def = (
            ("min", float, 1.0),
            ("max", float, None),
        )
        res = parse_args_from_str("1.23", arg_def)
        assert res == {"min": 1.23, "max": None}

        res = parse_args_from_str("", arg_def)
        assert res == {"min": 1.0, "max": None}, "'$name()' uses default args"

        arg_def = (
            ("name", str),
            ("hint", str, "test"),
        )
        res = parse_args_from_str("foo", arg_def)
        assert res == {"name": "foo", "hint": "test"}

        res = parse_args_from_str("", arg_def)
        assert res == {"name": "", "hint": "test"}

        res = parse_args_from_str(",", arg_def)
        assert res == {"name": "", "hint": ""}

        # Allow single and double quotes
        res = parse_args_from_str("'foo', ' bar '", arg_def)
        assert res == {"name": "foo", "hint": " bar "}

        res = parse_args_from_str('"foo", " bar "', arg_def)
        assert res == {"name": "foo", "hint": " bar "}

        arg_def = (
            ("name", str),
            ("amount", float),
            ("hint", str, "test"),
        )
        with pytest.raises(ValueError, match="Missing mandatory arg `amount.*"):
            parse_args_from_str("1.23", arg_def)

        # Allow $() macros
        arg_def = (("amount", float),)
        res = parse_args_from_str("$(def_amount)", arg_def)
        assert res == {"amount": "$(def_amount)"}

        # # Parse `$(context_key)` macros
        # ctx = {"base_url": "http://example.com", "def_amount": 7}
        # res = parse_args_from_str("$(base_url)/foo, $(def_amount)", arg_def, ctx)
        # assert res == {"name": "http://example.com/foo", "amount": 8, "hint": "test"}
