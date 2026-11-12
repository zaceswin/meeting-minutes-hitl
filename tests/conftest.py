import pytest

from minutes.demo import build_demo
from minutes.schemas import Session


@pytest.fixture
def demo_path(tmp_path):
    return build_demo(str(tmp_path))


@pytest.fixture
def demo(demo_path):
    return Session.load(demo_path)
