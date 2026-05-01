"""Fix pipeline_state.phase values to use SQLAlchemy enum member NAMES (uppercase).

SQLAlchemy 2.0 stores str-enum values using the member NAME (e.g. PHASE_4_STORY_DEPS)
not the member VALUE (phase_4_story_deps).  Migration q1r2s3t4u5v6 incorrectly
lowercased everything.  This migration corrects both the case and the phase numbers
after removing tasks (PHASE_8) and task_deps (PHASE_9) from the old 12-phase pipeline.

Final mapping (what should be in the DB after this migration):
  PHASE_1_EXTRACTION       (unchanged — same number)
  PHASE_2_EPICS            (unchanged)
  PHASE_3_STORIES          (unchanged)
  PHASE_4_STORY_DEPS       (was PHASE_5 before refinement removal)
  PHASE_5_PRIORITIZATION   (was PHASE_6)
  PHASE_6_CRITICAL_PATH    (was PHASE_7)
  PHASE_7_SPRINT_PLANNING  (was PHASE_10)
  PHASE_8_STAFFING         (was PHASE_11)
  PHASE_9_MONITORING       (was PHASE_12)

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-04-28
"""
from alembic import op

revision = 'r2s3t4u5v6w7'
down_revision = 'q1r2s3t4u5v6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Catch-all: handle every plausible old/intermediate value → correct NAME
    op.execute("""
        UPDATE project_management.pipeline_state
        SET phase = CASE phase
            -- phases 1-3: already correct number, just ensure uppercase NAME
            WHEN 'phase_1_extraction'      THEN 'PHASE_1_EXTRACTION'
            WHEN 'PHASE_1_EXTRACTION'      THEN 'PHASE_1_EXTRACTION'
            WHEN 'phase_2_epics'           THEN 'PHASE_2_EPICS'
            WHEN 'PHASE_2_EPICS'           THEN 'PHASE_2_EPICS'
            WHEN 'phase_3_stories'         THEN 'PHASE_3_STORIES'
            WHEN 'PHASE_3_STORIES'         THEN 'PHASE_3_STORIES'

            -- story_deps: was phase 5, now phase 4
            WHEN 'phase_4_story_deps'      THEN 'PHASE_4_STORY_DEPS'
            WHEN 'phase_5_story_deps'      THEN 'PHASE_4_STORY_DEPS'
            WHEN 'PHASE_5_STORY_DEPS'      THEN 'PHASE_4_STORY_DEPS'
            WHEN 'PHASE_4_STORY_DEPS'      THEN 'PHASE_4_STORY_DEPS'

            -- prioritization: was phase 6, now phase 5
            WHEN 'phase_5_prioritization'  THEN 'PHASE_5_PRIORITIZATION'
            WHEN 'phase_6_prioritization'  THEN 'PHASE_5_PRIORITIZATION'
            WHEN 'PHASE_6_PRIORITIZATION'  THEN 'PHASE_5_PRIORITIZATION'
            WHEN 'PHASE_5_PRIORITIZATION'  THEN 'PHASE_5_PRIORITIZATION'

            -- critical path: was phase 7, now phase 6
            WHEN 'phase_6_critical_path'   THEN 'PHASE_6_CRITICAL_PATH'
            WHEN 'phase_7_critical_path'   THEN 'PHASE_6_CRITICAL_PATH'
            WHEN 'PHASE_7_CRITICAL_PATH'   THEN 'PHASE_6_CRITICAL_PATH'
            WHEN 'PHASE_6_CRITICAL_PATH'   THEN 'PHASE_6_CRITICAL_PATH'

            -- sprint planning: was phase 10, now phase 7
            WHEN 'phase_7_sprint_planning' THEN 'PHASE_7_SPRINT_PLANNING'
            WHEN 'phase_10_sprint_planning' THEN 'PHASE_7_SPRINT_PLANNING'
            WHEN 'PHASE_10_SPRINT_PLANNING' THEN 'PHASE_7_SPRINT_PLANNING'
            WHEN 'PHASE_7_SPRINT_PLANNING'  THEN 'PHASE_7_SPRINT_PLANNING'

            -- staffing: was phase 11, now phase 8
            WHEN 'phase_8_staffing'        THEN 'PHASE_8_STAFFING'
            WHEN 'phase_11_staffing'       THEN 'PHASE_8_STAFFING'
            WHEN 'PHASE_11_STAFFING'       THEN 'PHASE_8_STAFFING'
            WHEN 'PHASE_8_STAFFING'        THEN 'PHASE_8_STAFFING'

            -- monitoring: was phase 12, now phase 9
            WHEN 'phase_9_monitoring'      THEN 'PHASE_9_MONITORING'
            WHEN 'phase_12_monitoring'     THEN 'PHASE_9_MONITORING'
            WHEN 'PHASE_12_MONITORING'     THEN 'PHASE_9_MONITORING'
            WHEN 'PHASE_9_MONITORING'      THEN 'PHASE_9_MONITORING'

            ELSE phase
        END
    """)

    # Remove any remaining rows for deleted phases
    op.execute("""
        DELETE FROM project_management.pipeline_state
        WHERE phase NOT IN (
            'PHASE_1_EXTRACTION', 'PHASE_2_EPICS', 'PHASE_3_STORIES',
            'PHASE_4_STORY_DEPS', 'PHASE_5_PRIORITIZATION',
            'PHASE_6_CRITICAL_PATH', 'PHASE_7_SPRINT_PLANNING',
            'PHASE_8_STAFFING', 'PHASE_9_MONITORING'
        )
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE project_management.pipeline_state
        SET phase = CASE phase
            WHEN 'PHASE_1_EXTRACTION'      THEN 'phase_1_extraction'
            WHEN 'PHASE_2_EPICS'           THEN 'phase_2_epics'
            WHEN 'PHASE_3_STORIES'         THEN 'phase_3_stories'
            WHEN 'PHASE_4_STORY_DEPS'      THEN 'phase_5_story_deps'
            WHEN 'PHASE_5_PRIORITIZATION'  THEN 'phase_6_prioritization'
            WHEN 'PHASE_6_CRITICAL_PATH'   THEN 'phase_7_critical_path'
            WHEN 'PHASE_7_SPRINT_PLANNING' THEN 'phase_10_sprint_planning'
            WHEN 'PHASE_8_STAFFING'        THEN 'phase_11_staffing'
            WHEN 'PHASE_9_MONITORING'      THEN 'phase_12_monitoring'
            ELSE phase
        END
    """)
