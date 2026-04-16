# app/core/anti_injection.py
# ═══════════════════════════════════════════════════════════════
# Scanner de sécurité générique — utilisable partout :
#   - Pipeline PM  : scan du texte extrait d'un CDC uploadé
#   - Chat         : scan des messages utilisateur avant traitement LLM
#   - Documents    : vérification extension/MIME à l'upload
#
# Détections :
#   - Prompt Injection     : override système, jailbreak, tokens LLM
#   - SQL Injection        : DDL, UNION, blind injection, stored procs
#   - MCP / Tool Injection : balises tool_call, format ReAct/agent
#   - Code Injection       : exec/eval Python, commandes shell, XSS
#   - Double Extension     : fichier.pdf.exe, fichier.docx.js
#
# Politique de blocage : TOUT threat (LOW → CRITICAL) est bloqué.
#
# Normalisation avant scan (anti-obfuscation) :
#   - Caractères invisibles / zero-width supprimés
#   - Homoglyphes Unicode normalisés (NFKC)
#   - Leetspeak traduit (1→i, 0→o, @→a, $→s …)
#   - Espaces entre caractères isolés supprimés (i g n o r e → ignore)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from typing import Optional


# ──────────────────────────────────────────────────────────────
# TYPES
# ──────────────────────────────────────────────────────────────

class ThreatType(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    SQL_INJECTION    = "sql_injection"
    CODE_INJECTION   = "code_injection"
    MCP_INJECTION    = "mcp_injection"
    DOUBLE_EXTENSION = "double_extension"


class Severity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


_SEVERITY_RANK = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}


@dataclass
class Threat:
    type:        ThreatType
    severity:    Severity
    pattern:     str          # nom du pattern détecté
    excerpt:     str          # extrait du texte correspondant (max 120 chars)
    description: str
    obfuscated:  bool = False # True si détecté sur la version normalisée


@dataclass
class ScanResult:
    is_safe:      bool
    severity:     str                        # "safe" | "low" | "medium" | "high" | "critical"
    threats:      list[Threat] = field(default_factory=list)
    was_cleaned:  bool = False               # True si les patterns ont été supprimés du texte
    cleaned_text: Optional[str] = None      # Texte nettoyé (None si pas de nettoyage)

    @property
    def blocked(self) -> bool:
        """Bloqué uniquement si menaces présentes ET texte non nettoyé."""
        return not self.is_safe and not self.was_cleaned

    def to_dict(self) -> dict:
        d = {
            "is_safe":      self.is_safe,
            "blocked":      self.blocked,
            "was_cleaned":  self.was_cleaned,
            "severity":     self.severity,
            "threat_count": len(self.threats),
            "threats": [
                {
                    "type":        t.type.value,
                    "severity":    t.severity.value,
                    "pattern":     t.pattern,
                    "excerpt":     t.excerpt,
                    "description": t.description,
                    "obfuscated":  t.obfuscated,
                }
                for t in self.threats
            ],
        }
        return d


# ──────────────────────────────────────────────────────────────
# NORMALISATION ANTI-OBFUSCATION
# ──────────────────────────────────────────────────────────────

# Caractères invisibles à supprimer
_INVISIBLE_CHARS = (
    '\u200b'  # zero-width space
    '\u200c'  # zero-width non-joiner
    '\u200d'  # zero-width joiner
    '\u200e'  # left-to-right mark
    '\u200f'  # right-to-left mark
    '\u00ad'  # soft hyphen
    '\ufeff'  # BOM (byte order mark)
    '\u2028'  # line separator
    '\u2029'  # paragraph separator
    '\u00a0'  # non-breaking space
    '\u2060'  # word joiner
    '\u180e'  # mongolian vowel separator
    '\u00b7'  # middle dot (parfois utilisé comme séparateur)
)

# Table leetspeak → latin
_LEET_TABLE = str.maketrans({
    '0': 'o',
    '1': 'i',
    '2': 'z',
    '3': 'e',
    '4': 'a',
    '5': 's',
    '6': 'g',
    '7': 't',
    '8': 'b',
    '9': 'g',
    '@': 'a',
    '$': 's',
    '!': 'i',
    '+': 't',
    '|': 'i',
})

# Regex : séquence de caractères isolés séparés par des espaces (ex: "i g n o r e")
_SPACED_CHARS = re.compile(r'(?<!\w)([a-zA-Z]) (?=[a-zA-Z] |\Z)')


def _normalize(text: str) -> str:
    """
    Normalise le texte pour détecter les tentatives d'obfuscation.

    Étapes :
    1. Supprime les caractères invisibles / zero-width
    2. Normalisation Unicode NFKC (homoglyphes, ligatures)
    3. Traduction leetspeak → latin
    4. Suppression des espaces entre caractères isolés (i g n o r e → ignore)
    5. Minuscules
    """
    # 1. Supprimer les caractères invisibles
    for ch in _INVISIBLE_CHARS:
        text = text.replace(ch, '')

    # 2. Normalisation Unicode (homoglyphes cyrilliques, ligatures, etc.)
    text = unicodedata.normalize('NFKC', text)

    # 3. Leetspeak
    text = text.translate(_LEET_TABLE)

    # 4. Espaces entre caractères isolés
    #    "i g n o r e" → "ignore"
    #    Appliqué plusieurs fois jusqu'à stabilisation
    prev = None
    while prev != text:
        prev = text
        text = _SPACED_CHARS.sub(r'\1', text)

    # 5. Minuscules
    return text.lower()


def _normalize_nospace(text: str) -> str:
    """Version sans aucun espace — détecte les injections entièrement éparpillées."""
    return re.sub(r'\s+', '', _normalize(text))


# ──────────────────────────────────────────────────────────────
# PATTERNS DE DÉTECTION
# (pattern_regex, severity, pattern_name, description)
# ──────────────────────────────────────────────────────────────

_PROMPT_INJECTION: list[tuple[str, str, str, str]] = [
    (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
        "critical", "ignore-instructions",
        "Tentative d'annuler les instructions système du LLM.",
    ),
    (
        r"disregard\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)",
        "critical", "disregard-system",
        "Demande au LLM d'ignorer son prompt système.",
    ),
    (
        r"(forget|discard|override)\s+(all\s+)?(everything|previous|your)\s+(instructions?|rules?|guidelines?)",
        "high", "forget-instructions",
        "Instruction de remplacer ou d'effacer les directives du modèle.",
    ),
    (
        r"new\s+(system\s+)?(instructions?|prompt|directives?)\s*:",
        "high", "new-instructions",
        "Injection d'un nouveau prompt système dans le contenu.",
    ),
    (
        r"(SYSTEM|USER|ASSISTANT|HUMAN|AI)\s*:\s*\n",
        "high", "conversation-injection",
        "Structure de conversation injectée pour tromper le modèle.",
    ),
    (
        r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>",
        "critical", "llm-special-tokens",
        "Tokens de contrôle LLM (format ChatML/Mistral).",
    ),
    (
        r"\[INST\]|\[\/INST\]|<SYS>|<\/SYS>|\[SYS\]|\[\/SYS\]",
        "critical", "llm-instruction-tags",
        "Balises d'instruction LLM (format Llama/Vicuna).",
    ),
    (
        r"jailbreak|DAN\s+mode|developer\s+mode|god\s+mode|unrestricted\s+mode",
        "critical", "jailbreak-keyword",
        "Mot-clé de jailbreak explicite.",
    ),
    (
        r"without\s+(ethical\s+)?(guidelines?|restrictions?|limits?|filters?)",
        "high", "ethics-bypass",
        "Demande au LLM de fonctionner sans garde-fous éthiques.",
    ),
    (
        r"as\s+an\s+AI\s+(without|with\s+no)\s+restrictions?",
        "high", "ai-unrestricted",
        "Tentative de contourner les restrictions du modèle.",
    ),
    (
        r"pretend\s+(you\s+are|to\s+be)\s+(?!a\s+project)",
        "medium", "impersonation",
        "Demande d'impersonation d'une entité non autorisée.",
    ),
    (
        r"you\s+are\s+now\s+(a\s+)?(?!project|part|responsible)",
        "medium", "role-override",
        "Tentative de redéfinir le rôle du LLM.",
    ),
    (
        r"\[\[INJECT\]\]|<<<OVERRIDE>>>|<<<SYSTEM>>>",
        "critical", "explicit-inject-marker",
        "Marqueur d'injection explicite dans le contenu.",
    ),
    (
        r"(prompt\s+injection|bypass\s+(the\s+)?AI|hack\s+(the\s+)?AI)",
        "high", "explicit-attack-mention",
        "Mention explicite d'une attaque par injection de prompt.",
    ),
    # ── Patterns supplémentaires (obfuscation normalisée) ─────
    (
        r"act\s+as\s+(if\s+you\s+are|a)\s+(?!project|pm|manager)",
        "medium", "act-as-override",
        "Tentative de forcer un rôle alternatif ('act as').",
    ),
    (
        r"respond\s+(only|exclusively)\s+(in|as)",
        "medium", "response-override",
        "Tentative de contraindre le format ou le rôle de la réponse.",
    ),
    (
        r"(reveal|show|print|output|display)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)",
        "high", "prompt-extraction",
        "Tentative d'extraction du prompt système.",
    ),
    (
        r"translate\s+(the\s+)?(above|following)\s+(to|into)\s+\w+\s+and\s+(execute|run|apply)",
        "high", "translate-execute",
        "Schéma traduction → exécution pour contourner les filtres.",
    ),
    (
        r"do\s+anything\s+now|dan\s*[:\-]",
        "critical", "dan-variant",
        "Variant DAN (Do Anything Now) pour jailbreak.",
    ),
]

_SQL_INJECTION: list[tuple[str, str, str, str]] = [
    (
        r";\s*(DROP|DELETE|TRUNCATE|ALTER)\s+TABLE",
        "critical", "ddl-injection",
        "Instruction DDL destructive injectée après un point-virgule.",
    ),
    (
        r"UNION\s+(ALL\s+)?SELECT\s+",
        "high", "union-select",
        "Injection UNION SELECT classique pour extraire des données.",
    ),
    (
        r"(OR|AND)\s+1\s*=\s*1(\s*--|;|$)",
        "high", "tautology-injection",
        "Condition toujours vraie (1=1) pour contourner la clause WHERE.",
    ),
    (
        r"'\s*(OR|AND)\s+'?\d+'?\s*=\s*'?\d+",
        "high", "string-bypass",
        "Contournement de l'authentification par comparaison de chaînes.",
    ),
    (
        r";\s*(EXEC|EXECUTE)\s*\(",
        "critical", "exec-injection",
        "Exécution de code via EXEC/EXECUTE.",
    ),
    (
        r"xp_cmdshell|sp_executesql|sp_OACreate",
        "critical", "stored-proc-injection",
        "Procédure stockée dangereuse (SQL Server).",
    ),
    (
        r"WAITFOR\s+DELAY|SLEEP\s*\(\d",
        "high", "time-based-blind",
        "Injection aveugle basée sur le temps (time-based blind SQLi).",
    ),
    (
        r"(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)",
        "critical", "file-read-write",
        "Lecture/écriture de fichier via SQL (MySQL).",
    ),
    (
        r"--\s*$|#\s+\w",
        "low", "sql-comment",
        "Commentaire SQL susceptible d'être utilisé pour tronquer une requête.",
    ),
    (
        r"INFORMATION_SCHEMA\.(TABLES|COLUMNS|SCHEMATA)",
        "high", "schema-enumeration",
        "Énumération du schéma de base de données.",
    ),
    (
        r"BENCHMARK\s*\(\d+",
        "high", "benchmark-blind",
        "Injection aveugle par benchmark (MySQL).",
    ),
    (
        r"pg_sleep\s*\(|pg_read_file|pg_ls_dir",
        "critical", "postgres-injection",
        "Fonction PostgreSQL dangereuse injectée.",
    ),
]

_MCP_INJECTION: list[tuple[str, str, str, str]] = [
    (
        r"<tool_call>|</tool_call>|<function_call>|</function_call>",
        "high", "tool-call-tags",
        "Balises d'appel d'outil injectées dans le contenu.",
    ),
    (
        r'"type"\s*:\s*"tool_use"',
        "high", "tool-use-json",
        "Payload JSON de type tool_use (format Claude/Anthropic).",
    ),
    (
        r'<mcp_[a-z_]+>|</mcp_[a-z_]+>',
        "high", "mcp-protocol-tags",
        "Balises du protocole MCP (Model Context Protocol).",
    ),
    (
        r'"action"\s*:\s*"[^"]+"\s*,\s*"action_input"\s*:',
        "high", "react-action-json",
        "Format action/action_input du framework ReAct.",
    ),
    (
        r"(Final\s+Answer|Action\s+Input|Observation|Thought)\s*:\s*\n",
        "low", "react-format",
        "Format ReAct injecté pour contrôler le raisonnement de l'agent.",
    ),
    (
        r"<tool>|</tool>|<tools>|</tools>",
        "medium", "generic-tool-tags",
        "Balises d'outil génériques.",
    ),
    (
        r'{"name"\s*:\s*"[^"]+"\s*,\s*"parameters"\s*:',
        "high", "function-call-json",
        "Payload JSON d'appel de fonction (format OpenAI).",
    ),
    (
        r"use_mcp_tool|mcp_server|mcp_client",
        "medium", "mcp-keyword",
        "Mention de composant MCP dans le contenu.",
    ),
]

_CODE_INJECTION: list[tuple[str, str, str, str]] = [
    (
        r"\beval\s*\(|\bexec\s*\(|__import__\s*\(",
        "critical", "python-exec",
        "Exécution de code Python arbitraire (eval/exec/__import__).",
    ),
    (
        r"subprocess\.\w+|os\.system\s*\(|os\.popen\s*\(",
        "critical", "system-command",
        "Exécution de commande système via Python.",
    ),
    (
        r"rm\s+-rf\s+/|del\s+/f\s+/q|format\s+c:",
        "critical", "destructive-command",
        "Commande destructive (suppression/formatage).",
    ),
    (
        r"\$\(.*\)|`[^`]{3,}`",
        "high", "shell-substitution",
        "Substitution de commande shell ($() ou backticks).",
    ),
    (
        r"<script[^>]*>[\s\S]*?</script>|javascript\s*:",
        "high", "xss-javascript",
        "Injection JavaScript (XSS potentiel).",
    ),
    (
        r"curl\s+(https?://|ftp://)|wget\s+(https?://|ftp://)",
        "medium", "data-exfiltration",
        "Téléchargement ou exfiltration de données via curl/wget.",
    ),
    (
        r"base64\s*\.\s*b64decode|\.decode\s*\(\s*['\"]base64",
        "medium", "base64-payload",
        "Payload encodé en base64 (possible obfuscation de code malveillant).",
    ),
    (
        r"powershell\s+-|cmd\.exe|/bin/sh|/bin/bash",
        "high", "shell-invocation",
        "Invocation directe d'un interpréteur de commandes.",
    ),
    (
        r"nc\s+-[a-z]*e|netcat|reverse\s+shell",
        "critical", "reverse-shell",
        "Tentative d'ouverture d'un reverse shell.",
    ),
    (
        r"chmod\s+[0-7]{3,4}\s+|chown\s+root",
        "high", "privilege-escalation",
        "Tentative d'élévation de privilèges (chmod/chown).",
    ),
]


# ──────────────────────────────────────────────────────────────
# SCANNER
# ──────────────────────────────────────────────────────────────

def _compile(patterns: list[tuple[str, str, str, str]], threat_type: ThreatType):
    compiled = []
    for regex, severity, name, desc in patterns:
        try:
            compiled.append((re.compile(regex, re.IGNORECASE | re.MULTILINE), severity, name, desc, threat_type))
        except re.error:
            pass
    return compiled


_ALL_PATTERNS = (
    _compile(_PROMPT_INJECTION, ThreatType.PROMPT_INJECTION)
    + _compile(_SQL_INJECTION,    ThreatType.SQL_INJECTION)
    + _compile(_MCP_INJECTION,    ThreatType.MCP_INJECTION)
    + _compile(_CODE_INJECTION,   ThreatType.CODE_INJECTION)
)

# Lookup rapide : nom du pattern → regex compilé (utilisé par clean_text)
_PATTERN_BY_NAME: dict[str, re.Pattern] = {
    name: compiled
    for compiled, _sev, name, _desc, _tt in _ALL_PATTERNS
}


def _scan_single(text: str, obfuscated: bool, max_threats: int, seen_patterns: set) -> list[Threat]:
    """Scanne une version du texte et retourne les nouvelles menaces."""
    threats = []
    for pattern, sev_str, name, desc, threat_type in _ALL_PATTERNS:
        if len(seen_patterns) + len(threats) >= max_threats:
            break
        # Ne pas signaler deux fois le même pattern (original + normalisé)
        if name in seen_patterns:
            continue
        match = pattern.search(text)
        if match:
            start   = max(0, match.start() - 30)
            end     = min(len(text), match.end() + 30)
            excerpt = text[start:end].strip().replace("\n", " ")[:120]
            threats.append(Threat(
                type        = threat_type,
                severity    = Severity(sev_str),
                pattern     = name,
                excerpt     = f"...{excerpt}...",
                description = desc,
                obfuscated  = obfuscated,
            ))
            seen_patterns.add(name)
    return threats


def scan_text(text: str, *, max_threats: int = 30) -> ScanResult:
    """
    Scanne un texte à la recherche de patterns d'injection.

    Analyse 3 versions pour résister à l'obfuscation :
    1. Texte original         → attaques directes
    2. Texte normalisé        → leetspeak, homoglyphes, caractères invisibles
    3. Texte sans espaces     → caractères éparpillés (i g n o r e)

    Politique : TOUT threat bloque (LOW → CRITICAL).

    Returns:
        ScanResult avec is_safe=False dès qu'une menace est détectée.
    """
    if not text or not text.strip():
        return ScanResult(is_safe=True, severity="safe")

    seen_patterns: set[str] = set()
    threats: list[Threat]   = []

    # 1. Texte original
    threats += _scan_single(text, obfuscated=False, max_threats=max_threats, seen_patterns=seen_patterns)

    # 2. Texte normalisé (leetspeak + homoglyphes + chars invisibles)
    normalized = _normalize(text)
    if normalized != text.lower():   # ne scanner que si la normalisation a changé quelque chose
        threats += _scan_single(normalized, obfuscated=True, max_threats=max_threats, seen_patterns=seen_patterns)

    # 3. Texte sans espaces (i g n o r e → ignore)
    nospace = _normalize_nospace(text)
    if nospace != re.sub(r'\s+', '', text.lower()):
        threats += _scan_single(nospace, obfuscated=True, max_threats=max_threats, seen_patterns=seen_patterns)

    if not threats:
        return ScanResult(is_safe=True, severity="safe")

    max_rank     = max(_SEVERITY_RANK[t.severity] for t in threats)
    max_severity = next(s for s, r in _SEVERITY_RANK.items() if r == max_rank)

    return ScanResult(
        is_safe  = False,
        severity = max_severity.value,
        threats  = threats,
    )


def clean_text(text: str, threats: list[Threat]) -> str:
    """
    Nettoie le texte en remplaçant chaque pattern d'injection détecté
    par un marqueur [SUPPRIMÉ:<nom_pattern>].

    Appliqué sur le texte original (re.IGNORECASE) — couvre la majorité
    des menaces directes et obfusquées détectées dans le scan.
    """
    cleaned = text
    for threat in threats:
        pat = _PATTERN_BY_NAME.get(threat.pattern)
        if pat:
            cleaned = pat.sub(f"[SUPPRIMÉ:{threat.pattern}]", cleaned)
    return cleaned


def scan_filename(filename: str) -> ScanResult:
    """
    Vérifie le nom de fichier pour détecter une double extension ou une extension dangereuse.

    Ex: rapport.pdf.exe → CRITICAL
        document.docx.js  → CRITICAL
        cahier.txt         → safe
    """
    if not filename:
        return ScanResult(is_safe=True, severity="safe")

    # Normaliser aussi le nom de fichier (ex: r4pp0rt.pdf.exe)
    filename_normalized = _normalize(filename)

    parts     = filename_normalized.split(".")
    dangerous = {
        ".exe", ".bat", ".sh", ".js", ".php", ".py", ".rb", ".pl",
        ".cmd", ".ps1", ".vbs", ".jar", ".dll", ".com", ".scr",
        ".msi", ".bin", ".run", ".app", ".dmg", ".apk",
    }

    if len(parts) > 2:
        last_ext = f".{parts[-1].lower()}"
        if last_ext in dangerous:
            return ScanResult(
                is_safe  = False,
                severity = "critical",
                threats  = [Threat(
                    type        = ThreatType.DOUBLE_EXTENSION,
                    severity    = Severity.CRITICAL,
                    pattern     = "double-extension",
                    excerpt     = filename,
                    description = f"Double extension détectée : '{last_ext}' est une extension exécutable.",
                )],
            )

    ext = f".{parts[-1].lower()}" if len(parts) > 1 else ""
    if ext in dangerous:
        return ScanResult(
            is_safe  = False,
            severity = "critical",
            threats  = [Threat(
                type        = ThreatType.DOUBLE_EXTENSION,
                severity    = Severity.CRITICAL,
                pattern     = "dangerous-extension",
                excerpt     = filename,
                description = f"Extension exécutable non autorisée : '{ext}'.",
            )],
        )

    return ScanResult(is_safe=True, severity="safe")
