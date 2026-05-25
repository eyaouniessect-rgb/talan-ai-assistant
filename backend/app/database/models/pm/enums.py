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


class PipelinePhaseEnum(str, enum.Enum):
    # Les 8 phases du pipeline IA (PHASE_7_SPRINT_PLANNING fusionnée dans le staffing).
    PHASE_1_EXTRACTION       = "phase_1_extraction"
    PHASE_2_EPICS            = "phase_2_epics"
    PHASE_3_STORIES          = "phase_3_stories"
    PHASE_4_STORY_DEPS       = "phase_4_story_deps"
    PHASE_5_PRIORITIZATION   = "phase_5_prioritization"
    PHASE_6_CRITICAL_PATH    = "phase_6_critical_path"
    # PHASE_7_SPRINT_PLANNING — DEPRECATED : la phase Sprints séparée a été
    # fusionnée dans le staffing (Step 3 — Story Distribution produit déjà les
    # sprints). Valeur conservée dans l'enum PG pour rétrocompatibilité ; les
    # rows existantes sont nettoyées par la migration w7x8y9z0a1b2.
    PHASE_7_SPRINT_PLANNING  = "phase_7_sprint_planning"
    PHASE_8_STAFFING         = "phase_8_staffing"
    PHASE_9_MONITORING       = "phase_9_monitoring"


class PipelineStatusEnum(str, enum.Enum):
    PENDING_AI         = "pending_ai"         # en attente de la réponse de l'agent IA
    PENDING_VALIDATION = "pending_validation" # l'IA a terminé, en attente du PM
    VALIDATED          = "validated"          # PM a approuvé → phase suivante débloquée
    REJECTED           = "rejected"           # PM a refusé → l'IA doit retravailler


class ProjectGlobalStatus(str, enum.Enum):
    NOT_STARTED    = "not_started"    # projet créé, aucune phase lancée
    IN_PROGRESS    = "in_progress"    # pipeline IA en cours
    PENDING_HUMAN  = "pending_human"  # une phase attend la validation du PM
    PIPELINE_DONE  = "pipeline_done"  # 9/9 phases validées — prêt pour le développement
    IN_DEVELOPMENT = "in_development" # développement en cours (progress 0→100)
    DELIVERED      = "delivered"      # projet livré (progress = 100)
