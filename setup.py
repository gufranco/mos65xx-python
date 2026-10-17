from setuptools import setup
from setuptools.command.build_py import build_py

TEST_MODULE_SUFFIX = ".test"


class WithoutTests(build_py):
    def find_package_modules(self, package: str, package_dir: str) -> list[tuple[str, str, str]]:
        found = super().find_package_modules(package, package_dir)
        return [one for one in found if not one[1].endswith(TEST_MODULE_SUFFIX)]


if __name__ == "__main__":
    setup(cmdclass={"build_py": WithoutTests})
