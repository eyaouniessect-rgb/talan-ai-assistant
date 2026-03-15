# Contrôle d'accès basé sur les rôles (Role-Based Access Control).
# Contient la table PERMISSIONS en base + la logique de vérification :
#   check_permission(role, action) → True / False
# Utilisé par le Node 2 de l'orchestrateur LangGraph.
# Exemple : consultant peut créer des congés, mais pas voir tous les projets.
