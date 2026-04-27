# models/pm/enums.py
# Schéma PostgreSQL : project_management
#
# Centralise tous les enums du schéma project_management.
# Importé par chaque fichier de table pm pour éviter les imports circulaires.

import enum


class EpicStatusEnum(str, enum.Enum):
    GENERATED = "generated"   # généré par l'IA (Phase 2) ou ajouté manuellement
    VALIDATED = "validated"   # validé par le PM (human-in-the-loop Phase 2)
    REJECTED  = "rejected"    # refusé lors de la validation humaine


class StoryStatusEnum(str, enum.Enum):
    GENERATED = "generated"   # générée par l'IA (Phase 3) ou ajoutée manuellement
    VALIDATED = "validated"
    REJECTED  = "rejected"


class TaskStatusEnum(str, enum.Enum):
    TODO        = "todo"
    IN_PROGRESS = "in_progress"
    DONE        = "done"
    BLOCKED     = "blocked"


class TaskTypeEnum(str, enum.Enum):
    FEATURE       = "feature"
    BUG           = "bug"
    DOCUMENTATION = "documentation"
    TESTING       = "testing"
    DEVOPS        = "devops"
    DESIGN        = "design"


class PipelinePhaseEnum(str, enum.Enum):
    # Les 11 phases correspondent exactement aux phases du pipeline IA
    PHASE_1_EXTRACTION       = "phase_1_extraction"
    PHASE_2_EPICS            = "phase_2_epics"
    PHASE_3_STORIES          = "phase_3_stories"
    PHASE_5_STORY_DEPS       = "phase_5_story_deps"
    PHASE_6_PRIORITIZATION   = "phase_6_prioritization"
    PHASE_7_TASKS            = "phase_7_tasks"
    PHASE_8_TASK_DEPS        = "phase_8_task_deps"
    PHASE_9_CRITICAL_PATH    = "phase_9_critical_path"
    PHASE_10_SPRINT_PLANNING = "phase_10_sprint_planning"
    PHASE_11_STAFFING        = "phase_11_staffing"
    PHASE_12_MONITORING      = "phase_12_monitoring"


class PipelineStatusEnum(str, enum.Enum):
    PENDING_AI         = "pending_ai"         # en attente de la réponse de l'agent IA
    PENDING_VALIDATION = "pending_validation" # l'IA a terminé, en attente du PM
    VALIDATED          = "validated"          # PM a approuvé → phase suivante débloquée
    REJECTED           = "rejected"           # PM a refusé → l'IA doit retravailler


class ProjectGlobalStatus(str, enum.Enum):
    NOT_STARTED    = "not_started"    # projet créé, aucune phase lancée
    IN_PROGRESS    = "in_progress"    # pipeline IA en cours
    PENDING_HUMAN  = "pending_human"  # une phase attend la validation du PM
    PIPELINE_DONE  = "pipeline_done"  # 11/11 phases validées — prêt pour le développement
    IN_DEVELOPMENT = "in_development" # développement en cours (progress 0→100)
    DELIVERED      = "delivered"      # projet livré (progress = 100)
