# Route dédiée au pipeline PM (analyse de CDC).
# POST /pipeline       → reçoit un fichier PDF/DOCX (CDC) → lance le pipeline LangGraph PM
#                        (extraction → MoSCoW → CPM → allocation ressources)
# Accessible uniquement aux utilisateurs avec role=pm (vérifié par middleware RBAC).
