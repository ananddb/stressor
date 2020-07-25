#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
from setuptools import setup


add_setup_opts = {}

if "bdist_msi" in sys.argv:

    try:
        # Only import cx_Freeze, when 'bdist_msi' command was used, because
        # cx_Freeze seems to sabotage wheel creation:
        from cx_Freeze import setup, Executable, hooks  # noqa F811

        # from cx_Freeze import hooks
        install_requires = ["lxml", "dateutil", "yaml", "requests", "sty"]
        # install_requires = ["lxml", "python-dateutil", "PyYAML", "requests", "sty"]
        # cx_Freeze seems to be confused by module name 'PyYAML' which
        # must be imported as 'yaml', so we rename here. However it must
        # be listed as 'PyYAML' in the requirements.txt and be installed!
        # install_requires.remove("PyYAML")
        # install_requires.append("yaml")

        # install_requires.remove("python-dateutil")
        # install_requires.append("dateutil")

        # Register  a  custom cxFreeze hook to fix some problems
        # (tested with cxFreeze 6.1)
        def load_stressor_hook(finder, module):
            print("hooks", finder, module)
            # No such file or directory: 'C:\Users\Martin\.virtualenvs\stressor-tMutAOFj\DLLs\libffi-7.dll'
            # if sys.platform == "win32" and sys.version_info >= (3, 8):
            #     dll_name = "libffi-7.dll"
            #     dll_path = os.path.join(sys.base_prefix, "DLLs", dll_name)
            #     finder.IncludeFiles(dll_path, os.path.join("lib", dll_name))
            # print("hooks", dll_path)

        setattr(hooks, "load_stressor", load_stressor_hook)

        add_setup_opts = {
            # Added to configuration from setup.cfg
            "executables": [
                Executable(
                    script="stressor/stressor_cli.py",
                    base=None,
                    # base="Win32GUI",
                    targetName="stressor.exe",
                    icon="docs/logo.ico",
                    shortcutName="stressor",
                    # requires cx_Freeze PR#94:
                    # copyright="(c) 2020 Martin Wendt",
                    # trademarks="...",
                )
            ],
            "options": {
                "build_exe": {
                    "includes": install_requires,
                    "include_files": [],
                    "packages": [
                        # "wsgidav.dir_browser",
                        # "wsgidav.dc.nt_dc",
                    ],
                    "excludes": ["tkinter"],
                    "constants": "BUILD_COPYRIGHT='(c) 2020 Martin Wendt'",
                    # "init_script": "Console",
                    "include_msvcr": True,
                },
                "bdist_msi": {
                    "upgrade_code": "{3DA14E9B-1D2A-4D90-92D0-2375CF66AC3D}",
                    "add_to_path": True,
                    "all_users": True,
                },
            },
        }
    except ImportError:
        # tox has problems to install cx_Freeze to it's venvs, but it is not
        # needed for the tests anyway
        print(
            "Could not import cx_Freeze; 'build' and 'bdist' commands will not be available."
        )
        print("See https://pypi.python.org/pypi/cx_Freeze")
else:
    print(
        "Did not import cx_Freeze, because 'bdist_msi' commands are not used ({}).".format(
            sys.argv
        )
    )
    print("NOTE: this is a hack, because cx_Freeze seemed to sabotage wheel creation")

setup(
    # See setup.cfg
    **add_setup_opts
)
