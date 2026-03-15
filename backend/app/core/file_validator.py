# Validation des fichiers uploadés par le PM (CDC).
# - Vérifie l'extension (liste blanche : .pdf, .docx)
# - Vérifie le type MIME réel (pas juste l'extension déclarée)
# - Double extension check : bloque les fichiers comme "rapport.pdf.exe"
# - Limite la taille : max 10 MB
