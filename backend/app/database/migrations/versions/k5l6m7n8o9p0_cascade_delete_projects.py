"""Ajouter ON DELETE CASCADE sur toutes les FK qui référencent crm.projects

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-04-21

Sans cascade, supprimer un projet lève une IntegrityError car pipeline_state,
epics, sprints et project_documents référencent encore projects.id.

Chaîne complète :
  crm.projects
    → project_management.pipeline_state  (CASCADE)
    → project_management.epics           (CASCADE)
        → project_management.user_stories    (CASCADE)
            → project_management.story_dependencies (CASCADE x2)
            → project_management.tasks          (CASCADE)
                → project_management.task_dependencies (CASCADE x2)
    → project_management.sprints         (CASCADE)
        ← project_management.tasks.sprint_id  (SET NULL — sprint nullable)
    → project_management.project_documents (CASCADE)
"""

from alembic import op


revision      = "k5l6m7n8o9p0"
down_revision = "j4k5l6m7n8o9"
branch_labels = None
depends_on    = None


def _recreate_fk(table, column, ref, schema, old_name, new_name, on_delete):
    op.drop_constraint(old_name, table, schema=schema, type_="foreignkey")
    op.create_foreign_key(
        new_name, table, ref[0],
        [column], [ref[1]],
        source_schema=schema,
        referent_schema=ref[2],
        ondelete=on_delete,
    )


def upgrade() -> None:
    pm = "project_management"

    # ── Direct FKs → crm.projects ────────────────────────────
    _recreate_fk("pipeline_state",   "project_id", ("projects", "id", "crm"), pm,
                 "pipeline_state_project_id_fkey",   "fk_pipeline_state_project_cascade",  "CASCADE")

    _recreate_fk("epics",            "project_id", ("projects", "id", "crm"), pm,
                 "epics_project_id_fkey",            "fk_epics_project_cascade",           "CASCADE")

    _recreate_fk("sprints",          "project_id", ("projects", "id", "crm"), pm,
                 "sprints_project_id_fkey",          "fk_sprints_project_cascade",         "CASCADE")

    _recreate_fk("project_documents","project_id", ("projects", "id", "crm"), pm,
                 "project_documents_project_id_fkey","fk_project_documents_project_cascade","CASCADE")

    # ── epics → user_stories ──────────────────────────────────
    _recreate_fk("user_stories",     "epic_id",    ("epics",    "id", pm),    pm,
                 "user_stories_epic_id_fkey",        "fk_user_stories_epic_cascade",       "CASCADE")

    # ── user_stories → story_dependencies ────────────────────
    _recreate_fk("story_dependencies","story_id",           ("user_stories","id",pm), pm,
                 "story_dependencies_story_id_fkey",           "fk_story_dep_story_cascade",         "CASCADE")
    _recreate_fk("story_dependencies","depends_on_story_id", ("user_stories","id",pm), pm,
                 "story_dependencies_depends_on_story_id_fkey","fk_story_dep_depends_cascade",       "CASCADE")

    # ── user_stories → tasks ─────────────────────────────────
    _recreate_fk("tasks",            "user_story_id",("user_stories","id",pm), pm,
                 "tasks_user_story_id_fkey",         "fk_tasks_story_cascade",             "CASCADE")

    # ── sprints → tasks.sprint_id (SET NULL : sprint supprimé ≠ tâche supprimée) ─
    _recreate_fk("tasks",            "sprint_id",  ("sprints",  "id", pm),    pm,
                 "tasks_sprint_id_fkey",             "fk_tasks_sprint_set_null",           "SET NULL")

    # ── tasks → task_dependencies ─────────────────────────────
    _recreate_fk("task_dependencies","task_id",           ("tasks","id",pm), pm,
                 "task_dependencies_task_id_fkey",            "fk_task_dep_task_cascade",           "CASCADE")
    _recreate_fk("task_dependencies","depends_on_task_id", ("tasks","id",pm), pm,
                 "task_dependencies_depends_on_task_id_fkey", "fk_task_dep_depends_cascade",        "CASCADE")


def downgrade() -> None:
    pm = "project_management"

    def _revert(table, column, ref, schema, old_name, new_name, on_delete_orig):
        op.drop_constraint(new_name, table, schema=schema, type_="foreignkey")
        op.create_foreign_key(old_name, table, ref[0], [column], [ref[1]],
                              source_schema=schema, referent_schema=ref[2])

    _revert("task_dependencies","depends_on_task_id",("tasks","id",pm),pm,
            "task_dependencies_depends_on_task_id_fkey","fk_task_dep_depends_cascade",None)
    _revert("task_dependencies","task_id",            ("tasks","id",pm),pm,
            "task_dependencies_task_id_fkey",           "fk_task_dep_task_cascade",  None)
    _revert("tasks",            "sprint_id",          ("sprints","id",pm),pm,
            "tasks_sprint_id_fkey","fk_tasks_sprint_set_null",None)
    _revert("tasks",            "user_story_id",      ("user_stories","id",pm),pm,
            "tasks_user_story_id_fkey","fk_tasks_story_cascade",None)
    _revert("story_dependencies","depends_on_story_id",("user_stories","id",pm),pm,
            "story_dependencies_depends_on_story_id_fkey","fk_story_dep_depends_cascade",None)
    _revert("story_dependencies","story_id",           ("user_stories","id",pm),pm,
            "story_dependencies_story_id_fkey","fk_story_dep_story_cascade",None)
    _revert("user_stories",     "epic_id",            ("epics","id",pm),pm,
            "user_stories_epic_id_fkey","fk_user_stories_epic_cascade",None)
    _revert("project_documents","project_id",         ("projects","id","crm"),pm,
            "project_documents_project_id_fkey","fk_project_documents_project_cascade",None)
    _revert("sprints",          "project_id",         ("projects","id","crm"),pm,
            "sprints_project_id_fkey","fk_sprints_project_cascade",None)
    _revert("epics",            "project_id",         ("projects","id","crm"),pm,
            "epics_project_id_fkey","fk_epics_project_cascade",None)
    _revert("pipeline_state",   "project_id",         ("projects","id","crm"),pm,
            "pipeline_state_project_id_fkey","fk_pipeline_state_project_cascade",None)
