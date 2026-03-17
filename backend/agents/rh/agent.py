# agents/rh/agent.py
from dotenv import load_dotenv
import os
import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from agents.rh import tools as rh_tools

load_dotenv()


class RHAgentExecutor(AgentExecutor):
    """
    Pont entre le protocole A2A et la logique métier RH.
    Conforme à la doc officielle A2A (comme PolicyAgentExecutor).
    """

    def __init__(self) -> None:
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            temperature=0,
        )

    async def _handle_intent(self, user_input: str, context_data: dict) -> str:
        """
        Analyse le message avec Gemini pour détecter l'intent
        puis appelle le bon tool directement.
        """
        # ── 1. Détection d'intent ──────────────────────────
        detection_prompt = f"""
Analyse ce message et retourne UNIQUEMENT un JSON valide, sans markdown.
Message : "{user_input}"

Intents possibles :
- create_leave          : créer un congé
- get_my_leaves         : consulter ses congés (tous ou filtrés par statut)
- get_team_availability : disponibilité équipe
- get_team_stack        : compétences équipe

Format :
{{
  "intent": "nom_intent",
  "entities": {{}}
}}

Exemples d'entités :
- create_leave  : {{"start_date": "2025-03-15", "end_date": "2025-03-21"}}
- get_my_leaves : {{"status_filter": "pending"}}   ← congés en attente
- get_my_leaves : {{"status_filter": "approved"}}  ← congés approuvés
- get_my_leaves : {{}}                              ← tous les congés
"""
        response = await self.llm.ainvoke([
            HumanMessage(content=detection_prompt)
        ])

        # ── 2. Parse JSON ──────────────────────────────────
        try:
            content = response.content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            parsed   = json.loads(content.strip())
            intent   = parsed.get("intent", "unknown")
            entities = parsed.get("entities", {})
        except Exception:
            intent   = "unknown"
            entities = {}

        user_id = context_data.get("user_id", 1)

        # ── 3. Appelle le bon tool ─────────────────────────
        if intent == "create_leave":
            start = entities.get("start_date")
            end   = entities.get("end_date")
            if not start or not end:
                return "Pour créer un congé, j'ai besoin des dates de début et de fin. Pouvez-vous me les préciser ? (format : YYYY-MM-DD)"
            result = await rh_tools.create_leave(
                user_id=user_id,
                start_date=start,
                end_date=end,
            )

        elif intent == "get_my_leaves":
            status_filter = entities.get("status_filter", None)
            result = await rh_tools.get_my_leaves(
                user_id=user_id,
                status_filter=status_filter
            )

        elif intent == "get_team_availability":
            result = await rh_tools.get_team_availability(user_id=user_id)

        elif intent == "get_team_stack":
            result = await rh_tools.get_team_stack(user_id=user_id)

        else:
            return "Je n'ai pas compris votre demande RH. Pouvez-vous reformuler ?"

        # ── 4. Formule une réponse naturelle ──────────────
        format_prompt = f"""
Tu es RHAgent, assistant RH de Talan Tunisie.
L'utilisateur a demandé : "{user_input}"

Voici les données exactes récupérées depuis la base de données :
{json.dumps(result, ensure_ascii=False, indent=2)}

RÈGLES STRICTES :
- Réponds DIRECTEMENT à la question posée
- Ne te présente PAS et ne liste PAS tes capacités
- Utilise UNIQUEMENT les données ci-dessus
- Si la liste est vide, dis-le clairement
- Affiche les données sous forme de liste claire et lisible
- Réponds toujours en français
"""
        final = await self.llm.ainvoke([
            HumanMessage(content=format_prompt)
        ])
        return final.content

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        user_input = context.get_user_input()
        try:
            result = await self._handle_intent(
                user_input=user_input,
                context_data={"user_id": 1},
            )
        except Exception as e:
            result = f"Erreur lors du traitement : {str(e)}"

        message = new_agent_text_message(result)
        await event_queue.enqueue_event(message)

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        pass