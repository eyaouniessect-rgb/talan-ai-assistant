# models/__init__.py
# Point d'entrée unique pour tous les modèles SQLAlchemy.
# Importer depuis ici garantit que toutes les classes sont connues de Base.metadata
# avant la génération des migrations Alembic.
# Ordre d'import : public → hris → crm → pm (respect des dépendances FK inter-schémas)

from .public import User, GoogleOAuthToken, Conversation, Message, Permission
from .hris import (
    Department, Team, Employee,
    Skill, EmployeeSkill,
    Leave, LeaveLog,
    CalendarEvent, CalendarEventLog,
)
from .crm import Client, Project, Assignment
from .pm import (
    PipelineState,
    Epic, UserStory, StoryDependency,
    Sprint, Task, TaskDependency,
)
