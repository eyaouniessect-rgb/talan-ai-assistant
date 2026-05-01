"""Rename pipeline_state.phase values after tasks/task_deps removal

The old Python PipelinePhaseEnum used uppercase values (PHASE_5_STORY_DEPS, ...).
The new enum uses lowercase + renumbered after removing refinement (phase 4),
tasks (phase 8) and task_deps (phase 9) from the original 12-phase pipeline.

Old (uppercase, stored in DB) → New (lowercase)
  PHASE_1_EXTRACTION      → phase_1_extraction      (same number)
  PHASE_2_EPICS           → phase_2_epics            (same number)
  PHASE_3_STORIES         → phase_3_stories          (same number)
  PHASE_4_REFINEMENT      → DELETE (already removed by m7n8o9p0q1r2)
  PHASE_5_STORY_DEPS      → phase_4_story_deps       (-1 after refinement)
  PHASE_6_PRIORITIZATION  → phase_5_prioritization   (-1)
  PHASE_7_CRITICAL_PATH   → phase_6_critical_path    (-1)
  PHASE_8_TASKS           → DELETE (removed)
  PHASE_9_TASK_DEPS       → DELETE (removed)
  PHASE_10_SPRINT_PLANNING → phase_7_sprint_planning  (-3)
  PHASE_11_STAFFING       → phase_8_staffing          (-3)
  PHASE_12_MONITORING     → phase_9_monitoring        (-3)

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-04-27
"""
from alembic import op

revision = 'q1r2s3t4u5v6'
down_revision = 'p0q1r2s3t4u5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Delete rows for removed phases ────────────────────
    op.execute("""
        DELETE FROM project_management.pipeline_state
        WHERE phase IN (
            'PHASE_4_REFINEMENT', 'phase_4_refinement',
            'PHASE_8_TASKS',      'phase_8_tasks',
            'PHASE_9_TASK_DEPS',  'phase_9_task_deps'
        )
    """)

    # ── 2. Rename uppercase old values → new lowercase values ─
    op.execute("""
        UPDATE project_management.pipeline_state
        SET phase = CASE phase
            WHEN 'PHASE_1_EXTRACTION'       THEN 'phase_1_extraction'
            WHEN 'PHASE_2_EPICS'            THEN 'phase_2_epics'
            WHEN 'PHASE_3_STORIES'          THEN 'phase_3_stories'
            WHEN 'PHASE_5_STORY_DEPS'       THEN 'phase_4_story_deps'
            WHEN 'PHASE_6_PRIORITIZATION'   THEN 'phase_5_prioritization'
            WHEN 'PHASE_7_CRITICAL_PATH'    THEN 'phase_6_critical_path'
            WHEN 'PHASE_10_SPRINT_PLANNING' THEN 'phase_7_sprint_planning'
            WHEN 'PHASE_11_STAFFING'        THEN 'phase_8_staffing'
            WHEN 'PHASE_12_MONITORING'      THEN 'phase_9_monitoring'
            ELSE phase
        END
        WHERE phase IN (
            'PHASE_1_EXTRACTION', 'PHASE_2_EPICS', 'PHASE_3_STORIES',
            'PHASE_5_STORY_DEPS', 'PHASE_6_PRIORITIZATION',
            'PHASE_7_CRITICAL_PATH', 'PHASE_10_SPRINT_PLANNING',
            'PHASE_11_STAFFING', 'PHASE_12_MONITORING'
        )
    """)

    # ── 3. Rename lowercase old-numbered → new lowercase values ──
    # Handles the case where some rows already used lowercase but old numbers
    op.execute("""
        UPDATE project_management.pipeline_state
        SET phase = CASE phase
            WHEN 'phase_5_story_deps'       THEN 'phase_4_story_deps'
            WHEN 'phase_6_prioritization'   THEN 'phase_5_prioritization'
            WHEN 'phase_7_critical_path'    THEN 'phase_6_critical_path'
            WHEN 'phase_10_sprint_planning' THEN 'phase_7_sprint_planning'
            WHEN 'phase_11_staffing'        THEN 'phase_8_staffing'
            WHEN 'phase_12_monitoring'      THEN 'phase_9_monitoring'
            ELSE phase
        END
        WHERE phase IN (
            'phase_5_story_deps', 'phase_6_prioritization',
            'phase_7_critical_path', 'phase_10_sprint_planning',
            'phase_11_staffing', 'phase_12_monitoring'
        )
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE project_management.pipeline_state
        SET phase = CASE phase
            WHEN 'phase_1_extraction'      THEN 'PHASE_1_EXTRACTION'
            WHEN 'phase_2_epics'           THEN 'PHASE_2_EPICS'
            WHEN 'phase_3_stories'         THEN 'PHASE_3_STORIES'
            WHEN 'phase_4_story_deps'      THEN 'PHASE_5_STORY_DEPS'
            WHEN 'phase_5_prioritization'  THEN 'PHASE_6_PRIORITIZATION'
            WHEN 'phase_6_critical_path'   THEN 'PHASE_7_CRITICAL_PATH'
            WHEN 'phase_7_sprint_planning' THEN 'PHASE_10_SPRINT_PLANNING'
            WHEN 'phase_8_staffing'        THEN 'PHASE_11_STAFFING'
            WHEN 'phase_9_monitoring'      THEN 'PHASE_12_MONITORING'
            ELSE phase
        END
        WHERE phase IN (
            'phase_1_extraction', 'phase_2_epics', 'phase_3_stories',
            'phase_4_story_deps', 'phase_5_prioritization',
            'phase_6_critical_path', 'phase_7_sprint_planning',
            'phase_8_staffing', 'phase_9_monitoring'
        )
    """)
