# -*- coding: utf-8 -*-
# (c) 2020 Martin Wendt and contributors; see https://github.com/mar10/stressor
# Licensed under the MIT license: https://www.opensource.org/licenses/mit-license.php
"""
"""
import itertools
import sys
import threading
import time
import webbrowser
from collections import defaultdict
from datetime import datetime

from stressor.config_manager import ConfigManager
from stressor.monitor.server import Monitor
from stressor.plugins.base import register_plugins
from stressor.session_manager import SessionManager, User
from stressor.statistic_manager import StatisticManager
from stressor.util import check_arg, get_dict_attr, logger, set_console_ctrl_handler


class RunManager:
    """
    Executes a run-configuration in parallel sessions.
    """

    CTRL_HANDLER_SET = None
    CURRENT_RUN_MANAGER = None

    DEFAULT_OPTS = {
        "monitor": False,
    }
    STAGES = (
        # "new",
        "ready",
        "running",
        "done",
        "waiting",
        "stopping",
        "stopped",
    )
    CHANNELS = (
        "log",
        "start_run",
        "start_session",
        "start_sequence",
        "start_activity",
        "end_activity",
        "end_sequence",
        "end_session",
        "end_run",
    )
    activity_map = {}

    def __init__(self):
        self.lock = threading.RLock()
        self.host_id = "h1"
        self.process_id = "p1"
        #: :class:`ConfigManager` used to load the configuration YAML
        self.config_manager = None
        self.has_hooks = False
        self.has_catch_all_hooks = False
        self._hooks = defaultdict(list)
        self.stop_request = threading.Event()
        #: (float): TODO: determines if a stop request is graceful or not
        #: Finalize the current sequence, then do 'end' sequence before stopping?
        self.stop_request_graceful = None
        self.session_list = []
        self.run_config = None
        self.stats = StatisticManager()
        self.options = self.DEFAULT_OPTS.copy()
        self.stage = "ready"
        self.start_dt = None
        self.end_dt = None

        register_plugins()
        self.CURRENT_RUN_MANAGER = self
        self.set_console_ctrl_handler()

    def __str__(self):
        # name = self.config_manager.path if self.config_manager else "?"
        # name = self.run_config.get("name") if self.run_config else "?"
        return "RunManager<{}>".format(self.stage.upper())

    @staticmethod
    def set_console_ctrl_handler():
        if RunManager.CTRL_HANDLER_SET is None:
            RunManager.CTRL_HANDLER_SET = set_console_ctrl_handler(
                RunManager._console_ctrl_handler
            )
            logger.info("set_console_ctrl_handler()")

    @staticmethod
    def _console_ctrl_handler(ctrl):
        # NOTE: seems that print/logger do not work here?
        # print("_console_ctrl_handler()")
        return RunManager.CURRENT_RUN_MANAGER.console_ctrl_handler(ctrl)

    def console_ctrl_handler(self, ctrl):
        """
        Args:
            ctrl (int): 0: CTRL_C_EVENT, 1: CTRL_BREAK_EVENT, 2: CTRL_CLOSE_EVENT
        Returns:
            True if handled
            False if not handled, i.e. next registered handler will be called
        """
        # if self.stop_request.is_set():
        #     print("Got Ctrl-C 2nd time: terminating...")
        #     logger.warning("Got Ctrl-C a 2nd time: terminating...")
        #     time.sleep(0.1)
        #     # sys.exit(2)
        print("Got Ctrl-C (windows handler), terminating...", file=sys.stderr)
        logger.warning("Got Ctrl-C (windows handler), terminating...")
        # self.stop_request.set()
        self.stop()
        # return False
        return True

    def set_stage(self, stage):
        check_arg(stage, str, stage in self.STAGES)
        logger.info("Enter stage '{}'".format(stage.upper()))
        self.stage = stage

    def publish(self, channel, allow_cancel=False, *args, **kwargs):
        """Notify all subscribed handlers."""
        assert channel in self.CHANNELS
        result_list = []
        if not self.has_hooks:
            return result_list

        channel_hooks = self._hooks.get(channel)
        generic_hooks = self._hooks.get("*")
        if channel_hooks:
            if generic_hooks:
                hooks = itertools.chain(channel_hooks, generic_hooks)
            else:
                hooks = channel_hooks
        elif generic_hooks:
            hooks = generic_hooks
        for handler in hooks:
            res = handler(channel, *args, **kwargs)
            if allow_cancel and res is False:
                return False
            result_list.append(res)
        return result_list

    def subscribe(self, channel, handler):
        self.has_hooks = True
        if channel == "*":
            self.has_catch_all_hooks = True
        else:
            assert channel in (self.CHANNELS)
        assert callable(handler)
        self._hooks[channel].append(handler)

    def has_errors(self, or_warnings=False):
        return self.stats.has_errors()

    def get_status_info(self):
        stats_info = self.stats.get_monitor_info()
        sessions = []
        for idx, sess in enumerate(self.session_list, 1):
            sessions.append(
                [
                    idx,
                    sess.session_id,
                    sess.user.name,
                    "n.a.",
                    sess.stats["activity.count"],
                    sess.stats["errors"],
                    str(sess.context_stack),
                ]
            )
        rc = self.run_config
        res = {
            "name": self.config_manager.name,
            "scenarioDetails": rc.get("details", "n.a."),
            "tag": rc.get("tag", "n.a."),
            "stage": self.stage,
            "hasErrors": self.has_errors(),
            "startTimeStr": "{}".format(self.start_dt.strftime("%Y-%m-%d %H:%M:%S")),
            "baseUrl": get_dict_attr(rc, "context.base_url"),
            "stats": stats_info,
            "sessions": sessions,
        }
        if self.end_dt:
            res["endTimeStr"] = "{} ({})".format(
                self.end_dt.strftime("%Y-%m-%d %H:%M:%S"), self.end_dt - self.start_dt
            )
        else:
            res["endTimeStr"] = "{}...".format(datetime.now() - self.start_dt)

        return res

    def log_info(self, *args, **kwargs):
        self.publish("log", level="info", *args, **kwargs)

    def load_config(self, run_config_file):
        """Load configuration file and set shortcuts."""
        cr = ConfigManager(self.stats)
        cr.read(run_config_file, load_files=True)

        self.config_manager = cr
        self.run_config = cr.run_config
        logger.info("Successfully compiled configuration {}.".format(cr.path))

    def _run_one(self, session_manager):
        """Run inside a separate thread."""
        try:
            session_manager.run()
            # We don't need to print results if only one session was run, since
            # it is also part of the global stats:
            rc = self.run_config
            if not rc.get("force_single") and rc["sessions"]["count"] > 1:
                logger.info(
                    "Results for {}:\n{}".format(
                        session_manager, session_manager.stats.format_result()
                    )
                )
        except KeyboardInterrupt:
            logger.exception("Session thread received Ctrl-C")
            self.stop_request.set()
            self.stats.inc("errors")
        except Exception:
            logger.exception("Session thread raised exception")
            self.stats.inc("errors")
            # raise
        return

    def run_in_threads(self, user_list, context):
        self.publish("start_run", run_manager=self)
        self.stop_request.clear()
        thread_list = []
        self.session_list = []
        for i, user in enumerate(user_list, 1):
            name = "t{}".format(i)
            sess = SessionManager(self, context, name, user)
            self.session_list.append(sess)
            t = threading.Thread(name=name, target=self._run_one, args=[sess])
            t.setDaemon(True)  # Required to make Ctrl-C work
            thread_list.append(t)

        logger.info("Starting session workers...")
        self.set_stage("running")
        start_run = time.time()
        for t in thread_list:
            t.start()

        logger.info("All session workers running, now waiting for them to terminate...")
        for t in thread_list:
            t.join()

        self.set_stage("done")
        elap = time.time() - start_run

        self.stats.add_timing("run", elap)

        self.publish("end_run", run_manager=self, elap=elap)

        logger.info("Results for {}:\n{}".format(self, self.stats.format_result()))

        error_count = self.has_errors()
        return error_count == 0

    def run(self, options, extra_context=None):
        """Run the current

        Args:
            context (dict):
        Returns:
            (int) Exit code 0 if no errors occured
        """
        check_arg(options, dict)
        check_arg(extra_context, dict, or_none=True)

        self.options.update(options)

        context = self.run_config["context"]
        if extra_context:
            context.update(extra_context)

        sessions = self.run_config["sessions"]

        count = int(sessions.get("count", 1))
        if count > 1 and self.run_config.get("force_single"):
            logger.info("force_single: restricting sessions count to one.")
            count = 1

        # Construct a `User` with at least 'name', 'password', and optional
        # custom attributes
        user_list = []
        for user_dict in sessions["users"]:
            user = User(**user_dict)
            user_list.append(user)
        # We have N users and want `count` sessions: re-use round-robin
        user_list = itertools.islice(itertools.cycle(user_list), 0, count)
        user_list = list(user_list)

        monitor = None
        if self.options.get("monitor"):
            monitor = Monitor(self)
            monitor.start()
            webbrowser.open_new_tab("http://127.0.0.1:8081/")

        self.start_dt = datetime.now()
        self.end_dt = None
        try:
            try:
                res = False
                res = self.run_in_threads(user_list, context)
            except KeyboardInterrupt:
                # if not self.stop_request.is_set():
                logger.warning("Caught Ctrl-C: terminating...")
                self.stop()
            finally:
                self.end_dt = datetime.now()

            if monitor:
                self.set_stage("waiting")
                self.stop_request.wait()
        finally:
            if monitor:
                monitor.shutdown()

            # print("RES", res, self.has_errors(), self.stats.format_result())
            self.set_stage("stopped")
        return res

    def stop(self, graceful=2):
        """"""
        # logger.info("Stop request received")
        self.set_stage("stopping")
        self.stop_request.set()
        return True
