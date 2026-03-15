# Logique principale de l'Agent RH.
# Initialise l'agent LangChain ReAct avec les outils RH.
# Le cycle ReAct : Reason → Act (appel MCP ou A2A) → Observe → Reason → ...
# agents/rh/agent.py
# RHAgentExecutor — pont entre le protocole A2A et la logique métier.
# Hérite de AgentExecutor (exactement comme PolicyAgentExecutor dans la doc officielle).
# agents/rh/agent.py
from dotenv import load_dotenv
import os
import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from agents.rh.prompts import RH_SYSTEM_PROMPT
from agents.rh import tools as rh_tools

load_dotenv()


class RHAgentExecutor(AgentExecutor):
    """
    Pont entre le protocole A2A et la logique métier RH.
    Conforme à la doc officielle A2A (comme PolicyAgentExecutor).
    Utilise Gemini directement sans AgentExecutor LangChain.
    """

    def __init__(self) -> None:
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            temperature=0,
        )

    async def _handle_intent(self, user_input: str, context_data: dict) -> str:
        """
        Analyse le message avec Gemini pour détecter l'intent
        puis appelle le bon tool directement.
        """
        # Demande à Gemini de détecter l'intent et les entités
        detection_prompt = f"""
Analyse ce message et retourne UNIQUEMENT un JSON :
Message : "{user_input}"

Intents possibles : create_leave, get_my_leaves, get_team_availability, get_team_stack

Format :
{{
  "intent": "nom_intent",
  "entities": {{}}
}}

Exemples d'entités :
- create_leave : {{"start_date": "2025-03-15", "end_date": "2025-03-21"}}
- autres : {{}}
"""
        response = await self.llm.ainvoke([
            HumanMessage(content=detection_prompt)
        ])

        # Parse la réponse
        try:
            content = response.content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            parsed = json.loads(content.strip())
            intent   = parsed.get("intent", "unknown")
            entities = parsed.get("entities", {})
        except Exception:
            intent   = "unknown"
            entities = {}

        user_id = context_data.get("user_id", 1)

        # Appelle le bon tool selon l'intent
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
            result = await rh_tools.get_my_leaves(user_id=user_id)

        elif intent == "get_team_availability":
            result = await rh_tools.get_team_availability(user_id=user_id)

        elif intent == "get_team_stack":
            result = await rh_tools.get_team_stack(user_id=user_id)

        else:
            return "Je n'ai pas compris votre demande RH. Pouvez-vous reformuler ?"

        # Demande à Gemini de formuler une réponse naturelle
        format_prompt = f"""
{RH_SYSTEM_PROMPT}

Voici le résultat brut de l'action "{intent}" :
{json.dumps(result, ensure_ascii=False, indent=2)}

Formule une réponse claire et naturelle en français pour l'utilisateur.
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
        # 1. Récupère le message utilisateur (doc officielle)
        user_input = context.get_user_input()

        # 2. Traite la demande
        try:
            result = await self._handle_intent(
                user_input=user_input,
                context_data={"user_id": 1},  # sera remplacé par le vrai user_id
            )
        except Exception as e:
            result = f"Erreur lors du traitement : {str(e)}"

        # 3. Retourne la réponse A2A (doc officielle)
        message = new_agent_text_message(result)
        await event_queue.enqueue_event(message)

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        pass