import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import app.main as main_module
from app.main import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    main_module._appointments = copy.deepcopy(main_module._SEED_DATA)
    with flask_app.test_client() as c:
        yield c
    main_module._appointments = copy.deepcopy(main_module._SEED_DATA)
