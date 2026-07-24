"""Register the Airflow 3.x auth client at import time."""

from drm.airflow.auth import Airflow3AuthClient
from drm.core.airflow_facade import register_client

register_client("airflow3", Airflow3AuthClient(), default=True)
