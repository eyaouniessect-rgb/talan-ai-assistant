from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

# Fix du path — pointe vers la racine backend/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

# Import unique via models/__init__.py — tous les modèles sont enregistrés sur Base.metadata
# Alembic détecte uniquement les modèles importés ici, d'où l'import global
from app.database.connection import Base
from app.database.models import (
    # public
    User, GoogleOAuthToken, Conversation, Message, Permission,
    # hris
    Department, Team, Employee,
    Skill, EmployeeSkill,
    Leave, LeaveLog,
    CalendarEvent, CalendarEventLog,
    # crm
    Client, Project, Assignment,
    # project_management
    PipelineState,
    Epic, UserStory, StoryDependency,
    Sprint, Task, TaskDependency,
)

config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
