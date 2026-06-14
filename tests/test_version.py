"""版本号契约测试。

`sshm.__version__` 是版本的唯一来源（pyproject 以 dynamic 从它读取）。
"""

import re

from sshm import __version__


def test_version_follows_semver():
    """__version__ 遵循语义化版本（MAJOR.MINOR.PATCH）。"""
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__
