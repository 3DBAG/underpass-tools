"""Build the small Zig C ABI library into the platform wheel."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        if prebuilt := os.getenv("UNDERPASS_ZIGPIP_PREBUILT"):
            shutil.copyfile(
                prebuilt,
                Path(self.build_lib)
                / "underpass_tools"
                / "zigpip"
                / Path(prebuilt).name,
            )
            return
        source = Path(__file__).parent / "native" / "zigpip"
        with tempfile.TemporaryDirectory() as directory:
            command = [
                os.getenv("ZIG", "zig"),
                "build",
                "-Doptimize=ReleaseFast",
                "--prefix",
                directory,
            ]
            if target := os.getenv("ZIG_TARGET"):
                command.append(f"-Dtarget={target}")
            subprocess.run(command, cwd=source, check=True)
            target = Path(self.build_lib) / "underpass_tools" / "zigpip"
            for library in (Path(directory) / "lib").glob("*zigpip*"):
                shutil.copyfile(library, target / library.name)


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True


setup(cmdclass={"build_py": BuildPy}, distclass=BinaryDistribution)
