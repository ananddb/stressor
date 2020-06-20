#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

from setuptools import Command, find_packages, setup
from setuptools.command.test import test as TestCommand

from stressor._version import __version__

version = __version__


# Override 'setup.py test' command
class ToxCommand(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # Import here, cause outside the eggs aren't loaded
        import tox

        # Raises SystemExit
        tox.cmdline(self.test_args)


# Add custom command 'setup.py sphinx'
# See https://dankeder.com/posts/adding-custom-commands-to-setup-py/
# and http://stackoverflow.com/a/22273180/19166
class SphinxCommand(Command):
    user_options = []
    description = "Build docs using Sphinx"

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import subprocess

        res = subprocess.call(
            "sphinx-build -b html docs/sphinx docs/sphinx-build", shell=True
        )
        outdir = os.path.join("docs", "sphinx-build")
        if res:
            print("ERROR: sphinx-build exited with code {}".format(res))
        else:
            print("Documentation created at {}.".format(os.path.abspath(outdir)))


try:
    readme = open("README.md", "rt").read()
except IOError:
    readme = "(Readme file not found. Running from tox/setup.py test?)"

# 'setup.py upload' fails on Vista, because .pypirc is searched on 'HOME' path
if "HOME" not in os.environ and "HOMEPATH" in os.environ:
    os.environ.setdefault("HOME", os.environ.get("HOMEPATH", ""))
    print("Initializing HOME environment variable to '{}'".format(os.environ["HOME"]))

use_cx_freeze = False
for cmd in ["bdist_msi"]:
    if cmd in sys.argv:
        use_cx_freeze = True
        break

# CherryPy is required for the tests and benchmarks. It is also the preferrred
# server for the stand-alone mode (`wsgidav.server.server_cli.py`).
# We currently do not add it as an installation requirement, because
#   1. users may not need the command line server at all
#   2. users may prefer another server
#   3. there may already cherrypy versions installed

install_requires = ["lxml", "python-dateutil", "PyYAML", "requests", "sty"]
setup_requires = install_requires
tests_require = []

if use_cx_freeze:
    # The Windows MSI Setup should include lxml, pywin32, and CherryPy
    install_requires.extend([])
    # Since we included pywin32 extensions, cx_Freeze tries to create a
    # version resource. This only supports the 'a.b.c[.d]' format:
    try:
        int_version = list(map(int, version.split(".")))
    except ValueError:
        # version = "0.0.0.{}".format(datetime.now().strftime("%Y%m%d"))
        version = "0.0.0"

    try:
        # Only import cx_Freeze, when 'bdist_msi' command was used, because
        # cx_Freeze seems to sabotage wheel creation:
        from cx_Freeze import setup, Executable  # noqa F811

        # from cx_Freeze import hooks

        # cx_Freeze seems to be confused by module name 'PyYAML' which
        # must be imported as 'yaml', so we rename here. However it must
        # be listed as 'PyYAML' in the requirements.txt and be installed!
        install_requires.remove("PyYAML")
        install_requires.append("yaml")

        install_requires.remove("python-dateutil")
        install_requires.append("dateutil")

        executables = [
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
        ]
    except ImportError:
        # tox has problems to install cx_Freeze to it's venvs, but it is not
        # needed for the tests anyway
        print(
            "Could not import cx_Freeze; 'build' and 'bdist' commands will not be available."
        )
        print("See https://pypi.python.org/pypi/cx_Freeze")
        executables = []
else:
    print(
        "Did not import cx_Freeze, because 'bdist_msi' commands are not used ({}).".format(
            sys.argv
        )
    )
    print("NOTE: this is a hack, because cx_Freeze seemed to sabotage wheel creation")
    executables = []


# https://stackoverflow.com/a/43034479/19166
PYTHON_INSTALL_DIR = os.path.dirname(os.path.dirname(os.__file__))
os.environ["TCL_LIBRARY"] = os.path.join(PYTHON_INSTALL_DIR, "tcl", "tcl8.6")
os.environ["TK_LIBRARY"] = os.path.join(PYTHON_INSTALL_DIR, "tcl", "tk8.6")

build_exe_options = {
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
}

bdist_msi_options = {
    "upgrade_code": "{3DA14E9B-1D2A-4D90-92D0-2375CF66AC3D}",
    "add_to_path": True,
    "all_users": True,
}

packages = find_packages(exclude=["test"])
print("setup.py: find_packages() -> {}".format(packages))

setup_opts = {
    # "name": "stressor",
    # "version": version,
    # "author": "Martin Wendt",
    # "author_email": "stressor@wwwendt.de",
    # "maintainer": "Martin Wendt",
    # "maintainer_email": "stressor@wwwendt.de",
    # "url": "https://github.com/mar10/stressor/",
    # "description": "Stress-test your web app",
    # "long_description": readme,
    # "long_description_content_type": "text/markdown",
    # "classifiers": [
    #     # "Development Status :: 3 - Alpha",
    #     "Development Status :: 4 - Beta",
    #     # "Development Status :: 5 - Production/Stable",
    #     "Environment :: Console",
    #     "Intended Audience :: Developers",
    #     "Intended Audience :: Information Technology",
    #     "Intended Audience :: System Administrators",
    #     "License :: OSI Approved :: MIT License",
    #     "Operating System :: OS Independent",
    #     "Programming Language :: Python",
    #     "Programming Language :: Python :: 3",
    #     "Programming Language :: Python :: 3.5",
    #     "Programming Language :: Python :: 3.6",
    #     "Programming Language :: Python :: 3.7",
    #     "Programming Language :: Python :: 3.8",
    #     "Topic :: Internet :: WWW/HTTP",
    #     "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    #     "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    #     "Topic :: Software Development :: Libraries :: Python Modules",
    #     "Topic :: Software Development :: Quality Assurance",
    #     "Topic :: Software Development :: Testing",
    #     "Topic :: Software Development :: Testing :: Traffic Generation",
    # ],
    # "keywords": "web server load test stress",
    # "license": "MIT",
    # "packages": packages,
    # "package_data": {
    #     # If any package contains *.txt files, include them:
    #     # "": ["*.css", "*.html", "*.ico", "*.js"],
    #     "": ["*.tmpl"],
    #     "stressor.monitor": ["htdocs/*.*"],
    # },
    # "install_requires": install_requires,
    # "setup_requires": setup_requires,
    # "tests_require": tests_require,
    # "py_modules": [],
    # "zip_safe": False,
    # "extras_require": {},
    # "cmdclass": {"test": ToxCommand, "sphinx": SphinxCommand},
    # "entry_points": {"console_scripts": ["stressor = stressor.stressor_cli:run"]},
    # "options": {},
}

if use_cx_freeze:
    setup_opts.update({"executables": executables})
    setup_opts["options"].update(
        {"build_exe": build_exe_options, "bdist_msi": bdist_msi_options}
    )

setup(**setup_opts)