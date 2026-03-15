# Protection contre les attaques d'injection :
# - Prompt Injection : sanitise et valide le contenu des messages avant d'envoyer au LLM
# - MCP Injection    : vérifie que les paramètres envoyés aux MCP servers sont propres
# - SQL Injection    : toujours utiliser SQLAlchemy ORM (jamais de requêtes brutes)
# - File Check       : vérifie l'extension et le contenu MIME des fichiers uploadés
#   → Double extension check : rapport.pdf.exe → rejeté
#   → Liste blanche : seulement .pdf et .docx acceptés pour le CDC
