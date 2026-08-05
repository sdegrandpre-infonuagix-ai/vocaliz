import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False is the whole point of naming it.
    #
    # fileConfig defaults to True, which disables every logger already configured — including
    # the one migrate_handler sets up at import. Lambda reuses a warm container, so one
    # migration silenced every scheduled invocation that followed it in that container: the
    # sweep and the xAI probe ran every minute and said nothing, for hours, and the absence
    # looked like a schedule that was not firing.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The app reads .env through pydantic-settings; Alembic runs outside the app, so
# load it here too or DATABASE_URL is unset and alembic.ini's empty url is used.
load_dotenv()

# Override sqlalchemy.url from environment
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # '%' must be doubled: set_main_option goes through configparser interpolation.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Import all models so Alembic can detect them
from src.database import Base  # noqa: E402
import src.models.user  # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
