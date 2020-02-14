# -*- coding: utf-8 -*-
# (c) 2020 Martin Wendt and contributors; see https://github.com/mar10/stressor
# Licensed under the MIT license: https://www.opensource.org/licenses/mit-license.php
"""
"""
import re
import time
from copy import deepcopy

import requests

from stressor.config_manager import replace_var_macros
from stressor.context_stack import ContextStack
from stressor.plugins.base import ActivityAssertionError
from stressor.statistic_manager import StatisticManager
from stressor.util import (
    NO_DEFAULT,
    check_arg,
    get_dict_attr,
    logger,
    shorten_string,
    StressorError,
)


class StoppedError(StressorError):
    """"""


class User:
    def __init__(self, name, password, **kwargs):
        self.name = name
        self.password = password
        for arg_name, arg_val in kwargs.items():
            assert type(arg_name) in (int, float, str)
            setattr(self, arg_name, arg_val)

    def __str__(self):
        return "User<{}>".format(self.name)

    @property
    def auth(self):
        """Return (name, password) tuple."""
        if self.password is None:
            return None
        return (self.name, self.password)


class SessionHelper:
    """Passed to script activities."""

    def __init__(self, session):
        self.__session = session

    @property
    def browser(self):
        return self.__session.browser_session


class SessionManager:
    """
    Run a scenario in a single session.
    """

    DEFAULT_TIMEOUT = 10.0

    def __init__(self, run_manager, context, session_id, user):
        # check_arg(run_manager, RunManager)
        check_arg(context, dict)
        check_arg(session_id, str)
        check_arg(user, User, or_none=True)

        #: The :class:`RunManager` object that holds global settings and definitions
        self.run_manager = run_manager
        #: (dict) Global variables for this session. Initialized from the
        #: run configuration, but not shared between sessions.
        context = context.copy()
        #: (str) Unique ID string for this session
        self.session_id = session_id
        #: The :class:`User` object that is assigned to this session
        self.user = user or User("anonymous", "")
        #: (dict) Copy of `run_config.sessions` configuration
        self.sessions = run_manager.run_config["sessions"].copy()
        #: (bool)
        self.dry_run = bool(context.get("dry_run"))
        #: (int)
        self.verbose = context.get("verbose", 3)
        #: (:class:`threading.Event`)
        self.stop_request = run_manager.stop_request

        context.setdefault("timeout", self.DEFAULT_TIMEOUT)
        context.setdefault("session_id", self.session_id)
        context.setdefault("user", self.user)

        #: The :class:`~stressor.context_stack.ContextStack` object that reflects the current execution path
        self.context_stack = ContextStack(run_manager.host_id, context)
        self.context_stack.push(run_manager.process_id)
        self.context_stack.push(session_id)
        #: :class:`~stressor.statistic_manager.StatisticManager` object that containscurrent execution path
        self.stats = StatisticManager(run_manager.stats)
        # Lazy initialization using a property
        self._browser_session = None
        self.fail_on_errors = False

    def __str__(self):
        return "SessionManager<{}>".format(self.session_id)

    def publish(self, channel, *args, **kwargs):
        kwargs["session_id"] = self.session_id
        return self.run_manager.publish(channel, *args, **kwargs)

    def _evaluate_macros(self, kwargs, context):
        replace_var_macros(kwargs, context)
        return kwargs

    def make_helper(self):
        """Return a :class:`SessionHelper` instance for this session."""
        res = SessionHelper(self)
        return res

    @property
    def browser_session(self):
        """Return a ``requests.Session`` instance for this session."""
        if self._browser_session is None:
            self._browser_session = requests.Session()
        return self._browser_session

    @property
    def context(self):
        return self.context_stack.context

    def get_context(self, dotted_key=None, default=NO_DEFAULT):
        res = self.context_stack.get_attr(dotted_key)
        return res

    def log_info(self, *args):
        logger.info(self.session_id, *args)
        # self.publish("log", self.session_id, *args, level="info")

    def has_errors(self, or_warnings=False):
        return self.stats["errors"] > 0

    def report_activity_start(self, activity):
        """Called by session runner before activities is executed."""
        logger.info(
            "{} {}: {}".format(
                "DRY-RUN" if self.dry_run else "Execute", self.context_stack, activity,
            )
        )
        if activity.raw_args.get("monitor"):
            self.stats["special.{}.".format(activity.compile_path)]

    def report_activity_error(self, activity, activity_args, exc):
        """Called session runner when activity `execute()` or assertions raise an error."""
        self.stats.inc("errors")

        # Create a copy of the current context, so we can shorten values
        context = self.context_stack.context.copy()
        context["last_result"] = shorten_string(context.get("last_result"), 100)

        msg = []
        # msg.append("{} {}: {!r}:".format(self.context_stack, activity, exc))
        msg.append("{!r}:".format(exc))
        if isinstance(exc, ActivityAssertionError):
            msg.append("Failed assertions:")
            for err in exc.assertion_list:
                msg.append("  - {}".format(err))
        msg.append("Execution path: {}".format(self.context_stack))
        msg.append("Activity: {}".format(activity))
        msg.append("Activity args: {}".format(activity_args))
        msg.append("Context: {}".format(context))

        msg = "\n    ".join(msg)
        logger.error(msg)

        if self.fail_on_errors:
            raise exc
        # self.results[level].append({"msg": msg, "path": path})
        return

    def report_activity_result(self, activity, activity_args, result, elap):
        """Called session runner when activity `execute()` or assertions raise an error."""

    def _process_activity_result(self, activity, activity_args, result, elap):
        """Perform common checks.

        Raises:
            ActivityAssertionError
        """
        context = self.context_stack.context
        errors = []
        # warnings = []

        arg = float(activity_args.get("assert_max_time", 0))
        if arg and elap > arg:
            errors.append(
                "Execution time limit of {} seconds exceeded: {:.3} sec.".format(
                    arg, elap
                )
            )

        arg = activity_args.get("assert_match")
        if arg:
            text = str(result)
            # Note: use re.search (not .match)!
            if not re.search(arg, text, re.MULTILINE):
                errors.append(
                    "Result does not match `{}`: {!r}".format(
                        arg, shorten_string(text, 100, 30)
                    )
                )

        arg = activity_args.get("store_json")
        if arg:
            for var_name, key_path in arg.items():
                try:
                    val = get_dict_attr(result, key_path)
                    context[var_name] = val
                except Exception:
                    errors.append(
                        "store_json could not find `{}` in activity result {!r}".format(
                            key_path, result
                        )
                    )

        if errors:
            raise ActivityAssertionError(errors)
        return

    def run_sequence(self, seq_name, sequence):
        stack = self.context_stack

        self.publish(
            "start_sequence", session=self, sequence=sequence, path=stack,
        )
        start_sequence = time.time()
        for act_idx, activity_args in enumerate(sequence, 1):
            activity_args = deepcopy(activity_args)
            activity = activity_args.pop("activity")

            with stack.enter("#{:02}-{}".format(act_idx, activity.get_script_name())):
                # with stack.enter("#{:02} {}".format(act_idx, activity_name)):
                context = stack.context

                expanded_args = self._evaluate_macros(activity_args, context)

                error = None
                result = None
                self.publish(
                    "start_activity",
                    session=self,
                    sequence=sequence,
                    activity=activity,
                    expanded_args=expanded_args,
                    context=context,
                    path=stack,
                )
                start_activity = time.time()

                self.report_activity_start(activity)

                try:
                    if self.stop_request.is_set():
                        raise StoppedError

                    result = activity.execute(self, **expanded_args)
                    context["last_result"] = result
                    # Evaluate standard `assert_...` and `store_...` clauses:
                    elap = time.time() - start_activity
                    self._process_activity_result(
                        activity, activity_args, result, elap,
                    )
                    self.report_activity_result(
                        activity, activity_args, result, elap,
                    )
                except (Exception, KeyboardInterrupt) as e:
                    if isinstance(e, KeyboardInterrupt):
                        self.stop_request.set()
                    error = e
                    self.report_activity_error(activity, activity_args, e)
                    if expanded_args.get("monitor"):
                        self.stats.add_error(activity, e)
                    # return False

                finally:
                    elap = time.time() - start_activity
                    self.stats.add_timing("activity", elap)
                    if expanded_args.get("monitor"):
                        self.stats.add_timing(activity, elap)
                    self.publish(
                        "end_activity",
                        session=self,
                        sequence=sequence,
                        path=stack,
                        activity=activity,
                        result=result,
                        error=error,
                        elap=elap,
                        context=context,
                    )

        elap = time.time() - start_sequence
        self.stats.add_timing("sequence." + seq_name, elap)
        self.publish(
            "end_sequence", session=self, sequence=sequence, path=stack, elap=elap,
        )
        context["last_result"] = None
        return self.stats["errors"] == 0

    def run(self):
        stack = self.context_stack
        rm = self.run_manager
        run_config = rm.run_config
        sequences = rm.config_manager.sequences
        scenario = run_config["scenario"]
        sessions = run_config["sessions"]
        session_duration = float(sessions.get("duration", 0))

        self.publish("start_session", session=self)

        start_session = time.time()
        skip_all = False
        skip_all_but_end = False

        for seq_idx, seq_def in enumerate(scenario, 1):
            seq_name = seq_def["sequence"]
            if skip_all or (skip_all_but_end and seq_name != "end"):
                logger.warning("Skipping sequence '{}'.".format(seq_name))
                continue
            self.stats.inc("sequence.count")
            sequence = sequences.get(seq_name)
            loop_repeat = int(seq_def.get("repeat", 0))
            loop_duration = float(seq_def.get("duration", 0))
            start_seq_loop = time.time()
            loop_idx = 0
            while True:
                loop_idx += 1
                # One single pass by default
                if not loop_repeat and not loop_duration and loop_idx > 1:
                    break
                # `Sequence repeat: COUNT`:
                if loop_repeat and loop_idx > loop_repeat:
                    break
                # `--single`:
                if loop_idx > 1 and run_config.get("force_single"):
                    logger.warning(
                        "force_single: sequence '{}' skipping remaining {} loops.".format(
                            seq_name, loop_repeat - 1 if loop_repeat else ""
                        )
                    )
                    break

                now = time.time()
                # `Sequence duration: SECS`:
                if loop_duration > 0 and now > (start_seq_loop + loop_duration):
                    logger.info(
                        "Stopping sequence '{}' loop after {} sec.".format(
                            seq_name, loop_duration
                        )
                    )
                    break
                # `Session duration: SECS` (but run 'end' sequence):
                elif (
                    seq_name != "end"
                    and session_duration > 0
                    and now > (start_session + session_duration)
                ):
                    logger.info(
                        "Stopping scenario '{}' loop after {} sec.".format(
                            seq_name, session_duration
                        )
                    )
                    skip_all_but_end = True
                    break

                with stack.enter("#{:02}-{}@{}".format(seq_idx, seq_name, loop_idx)):
                    is_ok = self.run_sequence(seq_name, sequence)
                    if seq_name == "init" and not is_ok:
                        logger.error(
                            "Stopping scenario due to an error in the 'init' sequence."
                        )
                        skip_all = True
                        break
                    elif self.stop_request.is_set():
                        logger.error("Stopping scenario due to a stop request.")
                        # TODO: a second 'ctrl-c' should not be so graceful
                        skip_all_but_end = True
                        break

        elap = time.time() - start_session
        self.stats.add_timing("session", elap)

        self.publish("end_session", session=self, elap=elap)

        # logger.info("Results for {}:\n{}".format(self, self.stats.format_result()))
        # print("RESULTS 2:\n{}".format(self.browser_session.stats))
        return not self.has_errors()
