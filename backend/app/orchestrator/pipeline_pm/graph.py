# Graphe LangGraph dédié au pipeline PM d'analyse de CDC.
# 6 nodes séquentiels :
#   Node 1 : Extraction du contenu du CDC (PDF/DOCX → texte)
#   Node 2 : Débat PO vs TL (simulation de priorisation contradictoire)
#   Node 3 : Priorisation MoSCoW (Must/Should/Could/Won't Have)
#   Node 4 : Graphe de dépendances entre les tâches
#   Node 5 : Calcul du chemin critique (CPM — Critical Path Method)
#   Node 6 : Allocation des ressources humaines recommandée
