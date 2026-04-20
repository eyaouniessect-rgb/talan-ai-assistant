# debug_slack_mcp.py — Lance depuis backend/
# python debug_slack_mcp.py
import asyncio
from agents.slack.mcp_client import list_tools, call_mcp
from dotenv import load_dotenv
load_dotenv()

async def main():

    # ── 1. Liste des outils disponibles ───────────────────
    print("\n" + "="*50)
    print("1. OUTILS MCP DISPONIBLES")
    print("="*50)
    try:
        tools = await list_tools()
        if tools:
            for t in tools:
                print(f"  ✅ {t['name']}")
        else:
            print("  ⚠️  Aucun outil retourné")
    except Exception as e:
        print(f"  ❌ ERREUR : {e}")
        print("  → Vérifie que supergateway tourne sur port 3001")
        return

    # ── 2. Lister les channels ─────────────────────────────
    print("\n" + "="*50)
    print("2. LISTE DES CHANNELS")
    print("="*50)
    try:
        r = await call_mcp("slack_list_channels", {})
        channels = r.get("channels", [])
        for ch in channels[:10]:
            print(f"  #{ch.get('name')} — ID: {ch.get('id')}")
        print(f"  → {len(channels)} channels trouvés")
    except Exception as e:
        print(f"  ❌ ERREUR slack_list_channels : {e}")

    # ── 3. Chercher Chaima Hermi ───────────────────────────
    print("\n" + "="*50)
    print("3. RECHERCHE UTILISATEUR : Chaima Hermi")
    print("="*50)
    try:
        r = await call_mcp("slack_get_users", {})
        members = r.get("members") or r.get("users") or []
        print(f"  → {len(members)} utilisateurs trouvés au total")

        # Filtrer par nom
        matches = []
        for m in members:
            profile = m.get("profile", {})
            real_name = (profile.get("real_name") or m.get("real_name") or "").lower()
            display_name = (profile.get("display_name") or "").lower()
            if "chaima" in real_name or "chaima" in display_name or "hermi" in real_name:
                matches.append(m)

        if matches:
            for m in matches:
                p = m.get("profile", {})
                print(f"  ✅ Trouvé : {p.get('real_name')} | ID: {m.get('id')} | Email: {p.get('email')}")
        else:
            print("  ⚠️  Chaima Hermi non trouvée")
            print("  → Premiers utilisateurs dans le workspace :")
            for m in members[:5]:
                p = m.get("profile", {})
                print(f"     - {p.get('real_name') or m.get('name')} | ID: {m.get('id')}")
    except Exception as e:
        print(f"  ❌ ERREUR slack_get_users : {e}")

    # ── 4. Envoyer un message test dans #canneau-test-talan-assistant ──
    print("\n" + "="*50)
    print("4. ENVOI MESSAGE TEST → #canneau-test-talan-assistant")
    print("="*50)
    channel_id = "C096MMUSYAV"   # ID du channel depuis l'URL Slack
    try:
        r = await call_mcp("slack_post_message", {
            "channel_id": channel_id,
            "text": "🤖 Test de l'agent Slack — Talan Assistant fonctionne correctement !",
        })
        print(f"  ✅ Message envoyé ! ts={r.get('ts')}")
    except Exception as e:
        print(f"  ❌ ERREUR slack_post_message : {e}")

    print("\n" + "="*50)
    print("FIN DES TESTS")
    print("="*50)


asyncio.run(main())
