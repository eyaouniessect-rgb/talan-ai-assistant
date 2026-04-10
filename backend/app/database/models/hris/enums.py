# models/hris/enums.py
# Schéma PostgreSQL : hris
#
# Centralise tous les enums du schéma hris.
# Importé par chaque fichier de table hris pour éviter les imports circulaires.

import enum


class DepartmentEnum(str, enum.Enum):
    INNOVATION_FACTORY = "innovation_factory"
    SALESFORCE         = "salesforce"
    DATA               = "data"
    DIGITAL_FACTORY    = "digital_factory"
    TESTING            = "testing"
    CLOUD              = "cloud"
    SERVICE_NOW        = "service_now"


class SeniorityEnum(str, enum.Enum):
    JUNIOR    = "junior"
    MID       = "mid"
    SENIOR    = "senior"
    LEAD      = "lead"       # Team Lead
    HEAD      = "head"       # Département Head
    PRINCIPAL = "principal"  # Directeur Général


class SkillLevelEnum(str, enum.Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    EXPERT       = "expert"


class LeaveTypeEnum(str, enum.Enum):
    ANNUAL      = "annual"       # Congé annuel
    MATERNITY   = "maternity"    # Congé maternité
    PATERNITY   = "paternity"    # Congé paternité
    BEREAVEMENT = "bereavement"  # Congé décès d'un proche
    UNPAID      = "unpaid"       # Congé sans solde
    SICK        = "sick"         # Congé maladie
    OTHER       = "other"


class LeaveStatusEnum(str, enum.Enum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    CANCELLED = "cancelled"
