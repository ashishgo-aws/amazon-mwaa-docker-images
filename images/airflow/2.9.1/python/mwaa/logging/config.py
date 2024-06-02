"""
A module which provides the logging configuration we use.

All loggers and handlers we use are defined here, both for Airflow and for our code.
For Airflow logging, we use their defaults and make the necessary changes to publish
logs to CloudWatch.

Airflow has a predefined list of loggers that are used throughout their code. For
example, a task logger called "airflow.task" is expected to be available for logs
related to tasks.

However, not everything being generated by Airflow uses the the standard Python logging
mechanism. For example, there is no single logger defined by Airflow that we can use to
capture all logs generated by the scheduler. Hence, to standardize the process, we run
sub-processes for cases like the schedulers, workers, etc., and then capture their
stdout and stderr and send them to a Python logger of our defining, e.g.
"mwaa.schedulers" for scheduler.
"""

# Python imports
import logging
import os

# 3rd party imports
from airflow.config_templates.airflow_local_settings import (
    BASE_LOG_FOLDER,
    DAG_PROCESSOR_MANAGER_LOG_LOCATION,
    DEFAULT_LOGGING_CONFIG,
    PROCESSOR_FILENAME_TEMPLATE,
)

# Our imports
from mwaa.logging import cloudwatch_handlers
from mwaa.utils import qualified_name

# We adopt the default logging configuration from Airflow and do the necessary changes
# to setup logging with CloudWatch Logs.
LOGGING_CONFIG = {
    **DEFAULT_LOGGING_CONFIG,
}


def _get_kms_key_arn():
    return os.environ.get("MWAA__CORE__KMS_KEY_ARN", None)


def _get_mwaa_logging_env_vars(source: str):
    log_group_arn = os.environ.get(
        f"MWAA__LOGGING__AIRFLOW_{source.upper()}_LOG_GROUP_ARN", None
    )
    log_level = os.environ.get(
        f"MWAA__LOGGING__AIRFLOW_{source.upper()}_LOG_LEVEL",
        logging.getLevelName(logging.INFO),
    )
    logging_enabled = os.environ.get(
        f"MWAA__LOGGING__AIRFLOW_{source.upper()}_LOGS_ENABLED", "false"
    )

    return (
        log_group_arn,
        log_level,
        logging_enabled.lower() == "true",
    )


def _configure_task_logging():
    log_group_arn, log_level, logging_enabled = _get_mwaa_logging_env_vars("task")
    if log_group_arn:
        # Setup CloudWatch logging.
        LOGGING_CONFIG["handlers"]["task"] = {
            "class": qualified_name(cloudwatch_handlers.TaskLogHandler),
            "formatter": "airflow",
            "filters": ["mask_secrets"],
            "base_log_folder": str(os.path.expanduser(BASE_LOG_FOLDER)),
            "log_group_arn": log_group_arn,
            "kms_key_arn": _get_kms_key_arn(),
            "enabled": logging_enabled,
        }
        LOGGING_CONFIG["loggers"]["airflow.task"].update(
            {
                "level": log_level,
            }
        )


def _configure_dag_processing_logging():
    log_group_arn, log_level, logging_enabled = _get_mwaa_logging_env_vars(
        "dagprocessor"
    )
    if log_group_arn:
        # Setup CloudWatch logging for DAG Processor Manager.
        LOGGING_CONFIG["handlers"]["processor_manager"] = {
            "class": qualified_name(cloudwatch_handlers.DagProcessorManagerLogHandler),
            "formatter": "airflow",
            "log_group_arn": log_group_arn,
            "kms_key_arn": _get_kms_key_arn(),
            "stream_name": os.path.basename(DAG_PROCESSOR_MANAGER_LOG_LOCATION),
            "enabled": logging_enabled,
        }
        LOGGING_CONFIG["loggers"]["airflow.processor_manager"] = {
            "handlers": ["processor_manager"],
            "level": log_level,
            "propagate": False,
        }

        # Setup CloudWatch logging for DAG processing.
        LOGGING_CONFIG["handlers"]["processor"] = {
            "class": qualified_name(cloudwatch_handlers.DagProcessingLogHandler),
            "formatter": "airflow",
            "log_group_arn": log_group_arn,
            "kms_key_arn": _get_kms_key_arn(),
            "stream_name_template": PROCESSOR_FILENAME_TEMPLATE,
            "enabled": logging_enabled,
        }
        LOGGING_CONFIG["loggers"]["airflow.processor"] = {
            "handlers": ["processor"],
            "level": log_level,
            "propagate": False,
        }


def _configure_subprocesses_logging(
    subprocess_name: str,
    log_group_arn: str | None,
    log_level: str,
    logging_enabled: bool,
):
    logger_name = MWAA_LOGGERS[subprocess_name.lower()]
    handler_name = logger_name.replace(".", "_")
    if log_group_arn:
        LOGGING_CONFIG["handlers"][handler_name] = {
            "class": qualified_name(cloudwatch_handlers.SubprocessLogHandler),
            "formatter": "airflow",
            "filters": ["mask_secrets"],
            "log_group_arn": log_group_arn,
            "kms_key_arn": _get_kms_key_arn(),
            "stream_name_prefix": subprocess_name.lower(),
            "logs_source": subprocess_name,
            "enabled": logging_enabled,
        }
        # Setup CloudWatch logging.
        LOGGING_CONFIG["loggers"][logger_name] = {
            "handlers": [handler_name],
            "level": log_level,
            "propagate": False,
        }


def _configure():
    _configure_task_logging()
    _configure_dag_processing_logging()
    # We run a standalone DAG Processor but we don't create a special logger for it
    # because Airflow already has a dedicated logger for it, so we just use that when
    # we run the "dag-processor" Airflow command.
    for comp in ["Worker", "Scheduler", "WebServer", "Triggerer"]:
        args = _get_mwaa_logging_env_vars(comp)
        _configure_subprocesses_logging(comp, *args)
        _configure_subprocesses_logging(f"{comp}_requirements", *args)


SCHEDULER_LOGGER_NAME = "mwaa.scheduler"
SCHEDULER_REQUIREMENTS_LOGGER_NAME = "mwaa.scheduler_requirements"
TRIGGERER_LOGGER_NAME = "mwaa.triggerer"
TRIGGERER_REQUIREMENTS_LOGGER_NAME = "mwaa.triggerer_requirements"
WEBSERVER_LOGGER_NAME = "mwaa.webserver"
WEBSERVER_REQUIREMENTS_LOGGER_NAME = "mwaa.webserver_requirements"
WORKER_LOGGER_NAME = "mwaa.worker"
WORKER_REQUIREMENTS_LOGGER_NAME = "mwaa.worker_requirements"

MWAA_LOGGERS = {
    "scheduler": SCHEDULER_LOGGER_NAME,
    "scheduler_requirements": SCHEDULER_REQUIREMENTS_LOGGER_NAME,
    "triggerer": TRIGGERER_LOGGER_NAME,
    "triggerer_requirements": TRIGGERER_REQUIREMENTS_LOGGER_NAME,
    "webserver": WEBSERVER_LOGGER_NAME,
    "webserver_requirements": WEBSERVER_REQUIREMENTS_LOGGER_NAME,
    "worker": WORKER_LOGGER_NAME,
    "worker_requirements": WORKER_REQUIREMENTS_LOGGER_NAME,
}

_configure()
