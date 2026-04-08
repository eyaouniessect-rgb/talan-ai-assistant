# scripts/seed_employees.py
# ═══════════════════════════════════════════════════════════
# Seed Talan Tunisie — employés répartis sur 7 départements
# + 1 utilisateur RH (sans profil employé)
#
# Départements : Innovation Factory, Salesforce, Data,
#                Digital Factory, Testing, Cloud, Service Now
#
# Exécution : python scripts/seed_employees.py
# ═══════════════════════════════════════════════════════════
import asyncio
import sys
import os
from datetime import date
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from passlib.context import CryptContext
from sqlalchemy import text
from app.database.connection import AsyncSessionLocal
from app.database.models.user import User
from app.database.models.hris import (
    Department, Team, Employee, Skill, EmployeeSkill,
    DepartmentEnum, SeniorityEnum, SkillLevelEnum,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEFAULT_PASSWORD = pwd_context.hash("Talan2026!")

# ─────────────────────────────────────────────────────────
# Départements & noms d'équipes
# ─────────────────────────────────────────────────────────

DEPARTMENTS = [
    DepartmentEnum.INNOVATION_FACTORY,
    DepartmentEnum.SALESFORCE,
    DepartmentEnum.DATA,
    DepartmentEnum.DIGITAL_FACTORY,
    DepartmentEnum.TESTING,
    DepartmentEnum.CLOUD,
    DepartmentEnum.SERVICE_NOW,
]

TEAM_NAMES = {
    DepartmentEnum.INNOVATION_FACTORY: ["Innovation Factory"],
    DepartmentEnum.SALESFORCE:         ["Salesforce Core", "Salesforce Delivery"],
    DepartmentEnum.DATA:               ["Data & Analytics", "Data Platform"],
    DepartmentEnum.DIGITAL_FACTORY:    ["Digital Factory", "Mobile Experience"],
    DepartmentEnum.TESTING:            ["Testing", "Quality Automation"],
    DepartmentEnum.CLOUD:              ["Cloud Ops", "Cloud Engineering"],
    DepartmentEnum.SERVICE_NOW:        ["ServiceNow", "ITSM Excellence"],
}

# ─────────────────────────────────────────────────────────
# Managers — 7 (1 par département)
# role="pm"
# ─────────────────────────────────────────────────────────
# (name, email, job_title, seniority, hire_date, dept)

# ─────────────────────────────────────────────────────────
# Dept Heads — 1 par département (manager_id = Behjet)
# Innovation Factory : Imen Ayari (défini dans INNOVATION_LEAD)
# (name, email, job_title, seniority, hire_date, dept)
# ─────────────────────────────────────────────────────────
DEPT_HEADS = [
    ("Sana Trabelsi",    "sana.trabelsi@talan.tn",   "Head of Salesforce",        SeniorityEnum.HEAD, date(2019, 6, 15), DepartmentEnum.SALESFORCE,       "Salesforce, CRM Strategy, Team Leadership, Apex, LWC"),
    ("Mohamed Gharbi",   "mohamed.gharbi@talan.tn",  "Head of Data",              SeniorityEnum.HEAD, date(2017, 9,  1), DepartmentEnum.DATA,             "Python, SQL, Power BI, Data Architecture, Team Leadership"),
    ("Ines Jebali",      "ines.jebali@talan.tn",     "Head of Digital Factory",   SeniorityEnum.HEAD, date(2020, 1, 10), DepartmentEnum.DIGITAL_FACTORY,  "React, Angular, Mobile Development, Agile, Team Leadership"),
    ("Karim Mzoughi",    "karim.mzoughi@talan.tn",   "Head of Testing",           SeniorityEnum.HEAD, date(2019, 4, 20), DepartmentEnum.TESTING,          "QA Strategy, Selenium, JIRA, Test Management, Team Leadership"),
    ("Walid Karray",     "walid.karray@talan.tn",    "Head of Cloud",             SeniorityEnum.HEAD, date(2018, 8,  5), DepartmentEnum.CLOUD,            "AWS, Azure, GCP, Cloud Architecture, Team Leadership"),
    ("Fatma Boubaker",   "fatma.boubaker@talan.tn",  "Head of ServiceNow",        SeniorityEnum.HEAD, date(2018, 11, 5), DepartmentEnum.SERVICE_NOW,      "ServiceNow, ITIL, ITSM, Platform Architecture, Team Leadership"),
]

# ─────────────────────────────────────────────────────────
# Team Leads — 1 par team (manager_id = Dept Head)
# Innovation Factory : pas de team lead séparé (Imen = head = team lead)
# (name, email, job_title, seniority, hire_date, dept, team_name)
# ─────────────────────────────────────────────────────────
TEAM_LEADS = [
    # Salesforce
    ("Wael Ben Amor",      "wael.benamor@talan.tn",      "Team Lead Salesforce Core",     SeniorityEnum.LEAD, date(2018, 7,  1), DepartmentEnum.SALESFORCE,      "Salesforce Core"),
    ("Lina Hamrouni",      "lina.hamrouni@talan.tn",     "Team Lead Salesforce Delivery", SeniorityEnum.LEAD, date(2019, 5,  1), DepartmentEnum.SALESFORCE,      "Salesforce Delivery"),
    # Data
    ("Khalil Mansouri",    "khalil.mansouri@talan.tn",   "Team Lead Data & Analytics",    SeniorityEnum.LEAD, date(2020, 4,  1), DepartmentEnum.DATA,            "Data & Analytics"),
    ("Sarra Ben Fredj",    "sarra.benfredj@talan.tn",    "Team Lead Data Platform",       SeniorityEnum.LEAD, date(2021, 1, 15), DepartmentEnum.DATA,            "Data Platform"),
    # Digital Factory
    ("Seif Tlili",         "seif.tlili@talan.tn",        "Team Lead Digital Factory",     SeniorityEnum.LEAD, date(2020, 2,  1), DepartmentEnum.DIGITAL_FACTORY, "Digital Factory"),
    ("Yasmine Baccar",     "yasmine.baccar@talan.tn",    "Team Lead Mobile Experience",   SeniorityEnum.LEAD, date(2019, 8,  1), DepartmentEnum.DIGITAL_FACTORY, "Mobile Experience"),
    # Testing
    ("Olfa Kchok",         "olfa.kchok@talan.tn",        "Team Lead Testing",             SeniorityEnum.LEAD, date(2018, 9,  1), DepartmentEnum.TESTING,         "Testing"),
    ("Riadh Louati",       "riadh.louati@talan.tn",      "Team Lead Quality Automation",  SeniorityEnum.LEAD, date(2019, 10, 1), DepartmentEnum.TESTING,         "Quality Automation"),
    # Cloud
    ("Hatem Brahem",       "hatem.brahem@talan.tn",      "Team Lead Cloud Ops",           SeniorityEnum.LEAD, date(2020, 9,  1), DepartmentEnum.CLOUD,           "Cloud Ops"),
    ("Zied Haddad",        "zied.haddad@talan.tn",       "Team Lead Cloud Engineering",   SeniorityEnum.LEAD, date(2020, 11, 1), DepartmentEnum.CLOUD,           "Cloud Engineering"),
    # ServiceNow
    ("Hamza Chaker",       "hamza.chaker@talan.tn",      "Team Lead ServiceNow",          SeniorityEnum.LEAD, date(2020, 8,  1), DepartmentEnum.SERVICE_NOW,     "ServiceNow"),
    ("Mouna Sfaxi",        "mouna.sfaxi@talan.tn",       "Team Lead ITSM Excellence",     SeniorityEnum.LEAD, date(2019, 3,  1), DepartmentEnum.SERVICE_NOW,     "ITSM Excellence"),
]

MANAGERS = DEPT_HEADS  # alias pour compatibilité avec le reste du code

# ─────────────────────────────────────────────────────────
# Consultants — base + cas d'ambiguïté de noms pour tests RH
# (name, email, job_title, seniority, hire_date, dept, skills)
# ─────────────────────────────────────────────────────────

CONSULTANTS = [
    # ── Innovation Factory (6) ─────────────────────────
    ("Yassine Eyaouni",   "eyaouniessect@gmail.com",    "Full Stack Developer",     SeniorityEnum.SENIOR, date(2022, 9,  1),  DepartmentEnum.INNOVATION_FACTORY, "React, Python, FastAPI, Node.js, PostgreSQL"),
    ("Yassine Cherif",    "yassine.cherif@talan.tn",    "Full Stack Developer",     SeniorityEnum.SENIOR, date(2021, 2,  1),  DepartmentEnum.INNOVATION_FACTORY, "React, Node.js, PostgreSQL"),
    ("Nour Hamdi",        "nour.hamdi@talan.tn",         "Software Architect",       SeniorityEnum.SENIOR, date(2020, 7, 15),  DepartmentEnum.INNOVATION_FACTORY, "Java, Microservices, Kafka"),
    ("Bilel Saad",        "bilel.saad@talan.tn",         "Backend Developer",        SeniorityEnum.MID,    date(2022, 3,  1),  DepartmentEnum.INNOVATION_FACTORY, "Python, FastAPI, Redis"),
    ("Rim Boughanmi",     "rim.boughanmi@talan.tn",      "Frontend Developer",       SeniorityEnum.MID,    date(2022, 6, 10),  DepartmentEnum.INNOVATION_FACTORY, "Vue.js, TypeScript, CSS"),
    ("Oussama Khediri",   "oussama.khediri@talan.tn",    "Software Engineer",        SeniorityEnum.JUNIOR, date(2024, 1, 15),  DepartmentEnum.INNOVATION_FACTORY, "Java, Spring Boot"),
    ("Asma Belhaj",       "asma.belhaj@talan.tn",        "Full Stack Developer",     SeniorityEnum.JUNIOR, date(2024, 9,  1),  DepartmentEnum.INNOVATION_FACTORY, "React, Python, Docker"),
    ("Ahmed Ben Salah",   "ahmed2.bensalah@talan.tn",    "Backend Developer",        SeniorityEnum.MID,    date(2023, 2,  1),  DepartmentEnum.INNOVATION_FACTORY, "Python, FastAPI, PostgreSQL"),

    # ── Salesforce ────────────────────────────────────
    # Salesforce Core
    ("Mariem Karray",     "mariem.karray@talan.tn",      "Salesforce Developer",     SeniorityEnum.SENIOR, date(2020, 3,  1),  DepartmentEnum.SALESFORCE, "Apex, LWC, SOQL"),
    ("Tarek Slimani",     "tarek.slimani@talan.tn",      "Salesforce Admin",         SeniorityEnum.MID,    date(2021, 8, 15),  DepartmentEnum.SALESFORCE, "Salesforce Admin, Flows"),
    ("Anis Melliti",      "anis.melliti@talan.tn",       "Salesforce Developer",     SeniorityEnum.MID,    date(2022, 1, 10),  DepartmentEnum.SALESFORCE, "Apex, Triggers, Integration"),
    # Salesforce Delivery
    ("Ghofrane Ayadi",    "ghofrane.ayadi@talan.tn",     "Salesforce Consultant",    SeniorityEnum.JUNIOR, date(2024, 3,  1),  DepartmentEnum.SALESFORCE, "Salesforce, Flows"),
    ("Nour Hamdi",        "nour2.hamdi@talan.tn",        "Salesforce Consultant",    SeniorityEnum.MID,    date(2023, 6, 10),  DepartmentEnum.SALESFORCE, "Salesforce, CRM, Flows"),

    # ── Data ──────────────────────────────────────────
    # Data & Analytics
    ("Firas Guesmi",      "firas.guesmi@talan.tn",       "ML Engineer",              SeniorityEnum.MID,    date(2022, 5,  1),  DepartmentEnum.DATA, "PyTorch, MLflow, Azure ML"),
    ("Amira Triki",       "amira.triki@talan.tn",        "Data Analyst",             SeniorityEnum.MID,    date(2022, 9,  1),  DepartmentEnum.DATA, "SQL, Power BI, Python"),
    ("Rania Chouchane",   "rania.chouchane@talan.tn",    "Data Scientist",           SeniorityEnum.MID,    date(2023, 3, 15),  DepartmentEnum.DATA, "Python, NLP, Scikit-learn"),
    # Data Platform
    ("Hichem Dhouib",     "hichem.dhouib@talan.tn",      "Data Engineer",            SeniorityEnum.JUNIOR, date(2024, 2,  1),  DepartmentEnum.DATA, "Python, dbt, Snowflake"),
    ("Mohamed Gharbi",    "mohamed2.gharbi@talan.tn",    "Data Analyst",             SeniorityEnum.MID,    date(2022, 12, 1),  DepartmentEnum.DATA, "SQL, Power BI, Python"),

    # ── Digital Factory ───────────────────────────────
    # Digital Factory
    ("Malek Hamza",       "malek.hamza@talan.tn",         "Mobile Developer",         SeniorityEnum.MID,    date(2022, 4,  1),  DepartmentEnum.DIGITAL_FACTORY, "Flutter, React Native"),
    ("Sami Bouri",        "sami.bouri@talan.tn",          "Backend Developer",        SeniorityEnum.MID,    date(2022, 8,  1),  DepartmentEnum.DIGITAL_FACTORY, "Node.js, Express, MongoDB"),
    # Mobile Experience
    ("Houda Ben Youssef", "houda.benyoussef@talan.tn",    "Full Stack Developer",     SeniorityEnum.MID,    date(2023, 1, 10),  DepartmentEnum.DIGITAL_FACTORY, "Angular, .NET, SQL Server"),
    ("Nizar Jaziri",      "nizar.jaziri@talan.tn",        "Frontend Developer",       SeniorityEnum.JUNIOR, date(2024, 9,  1),  DepartmentEnum.DIGITAL_FACTORY, "React, CSS, JavaScript"),

    # ── Testing ───────────────────────────────────────
    # Testing
    ("Amel Smiri",        "amel.smiri@talan.tn",          "QA Engineer",              SeniorityEnum.SENIOR, date(2020, 6,  1),  DepartmentEnum.TESTING, "Selenium, Cypress, JIRA"),
    ("Jihen Chaari",      "jihen.chaari@talan.tn",        "Performance Tester",       SeniorityEnum.MID,    date(2022, 2,  1),  DepartmentEnum.TESTING, "JMeter, Gatling, K6"),
    # Quality Automation
    ("Hela Fersi",        "hela.fersi@talan.tn",          "QA Engineer",              SeniorityEnum.JUNIOR, date(2024, 4,  1),  DepartmentEnum.TESTING, "Cypress, Postman, JIRA"),
    ("Montassar Zribi",   "montassar.zribi@talan.tn",     "Test Automation Engineer", SeniorityEnum.MID,    date(2023, 5,  1),  DepartmentEnum.TESTING, "Playwright, Selenium, Python"),

    # ── Cloud ─────────────────────────────────────────
    # Cloud Ops
    ("Achref Mejri",      "achref.mejri@talan.tn",        "Cloud Engineer",           SeniorityEnum.MID,    date(2022, 7,  1),  DepartmentEnum.CLOUD, "AWS, GCP, Terraform"),
    ("Maroua Zahouani",   "maroua.zahouani@talan.tn",     "Cloud Infrastructure Eng", SeniorityEnum.MID,    date(2022, 11, 1),  DepartmentEnum.CLOUD, "Azure, Terraform, Ansible"),
    # Cloud Engineering
    ("Lotfi Ben Nasr",    "lotfi.bennasr@talan.tn",       "DevSecOps Engineer",       SeniorityEnum.SENIOR, date(2020, 1, 15),  DepartmentEnum.CLOUD, "Docker, Kubernetes, Security"),
    ("Cyrine Ferchichi",  "cyrine.ferchichi@talan.tn",    "DevOps Engineer",          SeniorityEnum.MID,    date(2023, 5,  1),  DepartmentEnum.CLOUD, "Docker, CI/CD, Jenkins"),
    ("Imen Zouaghi",      "imen.zouaghi@talan.tn",        "Cloud Engineer",           SeniorityEnum.JUNIOR, date(2024, 6,  1),  DepartmentEnum.CLOUD, "AWS, Python, Terraform"),

    # ── ServiceNow ────────────────────────────────────
    # ServiceNow
    ("Aymen Tlili",       "aymen.tlili@talan.tn",         "ServiceNow Admin",         SeniorityEnum.MID,    date(2022, 11, 1),  DepartmentEnum.SERVICE_NOW, "ServiceNow Admin, Workflows"),
    ("Chaima Bougzala",   "chaima.bougzala@talan.tn",     "Platform Developer",       SeniorityEnum.MID,    date(2023, 2,  1),  DepartmentEnum.SERVICE_NOW, "ServiceNow, REST API, Angular"),
    ("Walid Ben Hadj",    "walid.benhadj@talan.tn",       "ServiceNow Developer",     SeniorityEnum.JUNIOR, date(2024, 7,  1),  DepartmentEnum.SERVICE_NOW, "ServiceNow, JavaScript"),
    # ITSM Excellence
    ("Samia Miled",       "samia.miled@talan.tn",         "ITSM Consultant",          SeniorityEnum.MID,    date(2021, 9,  1),  DepartmentEnum.SERVICE_NOW, "ITIL, ServiceNow, Process Design"),
    ("Chaima Bougzala",   "chaima2.bougzala@talan.tn",    "ITSM Consultant",          SeniorityEnum.JUNIOR, date(2024, 10, 1),  DepartmentEnum.SERVICE_NOW, "ServiceNow, ITIL"),
]

# ─────────────────────────────────────────────────────────
# Directeur Général — manager de tous les managers
# ─────────────────────────────────────────────────────────
DIRECTOR = ("Behjet Boussofara", "behjet.boussofara@talan.tn", "Directeur Général", SeniorityEnum.PRINCIPAL, date(2015, 1, 1), DepartmentEnum.INNOVATION_FACTORY)

# Lead Innovation Factory — sous Behjet, au-dessus des consultants IF
INNOVATION_LEAD = ("Imen Ayari", "imen.ayari@talan.tn", "Innovation Factory Lead", SeniorityEnum.HEAD, date(2017, 6, 1), DepartmentEnum.INNOVATION_FACTORY)

# ─────────────────────────────────────────────────────────
# Skills par email — pour Directeur, Innovation Lead, Dept Heads, Team Leads
# (les consultants ont leurs skills définis dans le tuple CONSULTANTS)
# ─────────────────────────────────────────────────────────
SKILLS_MAP: dict[str, str] = {
    # Directeur Général
    "behjet.boussofara@talan.tn": "Leadership, Strategy, Business Development, Agile, Change Management",
    # Innovation Factory Lead
    "imen.ayari@talan.tn": "Innovation Management, Agile, Product Design, Lean Startup, Team Leadership",
    # Dept Heads
    "sana.trabelsi@talan.tn":   "Salesforce, CRM Strategy, Apex, LWC, Team Leadership",
    "mohamed.gharbi@talan.tn":  "Python, SQL, Power BI, Data Architecture, Team Leadership",
    "ines.jebali@talan.tn":     "React, Angular, Mobile Development, Agile, Team Leadership",
    "karim.mzoughi@talan.tn":   "QA Strategy, Selenium, JIRA, Test Management, Team Leadership",
    "walid.karray@talan.tn":    "AWS, Azure, GCP, Cloud Architecture, Team Leadership",
    "fatma.boubaker@talan.tn":  "ServiceNow, ITIL, ITSM, Platform Architecture, Team Leadership",
    # Team Leads
    "wael.benamor@talan.tn":    "Apex, LWC, Salesforce, SOQL, Agile",
    "lina.hamrouni@talan.tn":   "Salesforce, Flows, CRM, Integration, Project Management",
    "khalil.mansouri@talan.tn": "Python, SQL, Power BI, MLflow, Agile",
    "sarra.benfredj@talan.tn":  "dbt, Snowflake, Python, Spark, Data Architecture",
    "seif.tlili@talan.tn":      "React, Angular, Node.js, TypeScript, Agile",
    "yasmine.baccar@talan.tn":  "Flutter, React Native, iOS, Android, UX Design",
    "olfa.kchok@talan.tn":      "Selenium, Cypress, JIRA, Test Strategy, Agile",
    "riadh.louati@talan.tn":    "Playwright, Selenium, Python, CI/CD, Test Architecture",
    "hatem.brahem@talan.tn":    "AWS, GCP, Terraform, Kubernetes, SRE",
    "zied.haddad@talan.tn":     "Docker, Kubernetes, CI/CD, Security, Cloud Architecture",
    "hamza.chaker@talan.tn":    "ServiceNow, JavaScript, REST API, Workflows, Agile",
    "mouna.sfaxi@talan.tn":     "ITIL, ServiceNow, Process Design, ITSM, Project Management",
}

# ─────────────────────────────────────────────────────────
# Numéros de téléphone par email
# ─────────────────────────────────────────────────────────
PHONES_MAP: dict[str, str] = {
    # Directeur
    "behjet.boussofara@talan.tn": "+216 71 100 001",
    # Innovation Factory Lead
    "imen.ayari@talan.tn":        "+216 20 100 002",
    # Dept Heads
    "sana.trabelsi@talan.tn":     "+216 20 200 001",
    "mohamed.gharbi@talan.tn":    "+216 20 200 002",
    "ines.jebali@talan.tn":       "+216 20 200 003",
    "karim.mzoughi@talan.tn":     "+216 20 200 004",
    "walid.karray@talan.tn":      "+216 20 200 005",
    "fatma.boubaker@talan.tn":    "+216 20 200 006",
    # Team Leads
    "wael.benamor@talan.tn":      "+216 20 300 001",
    "lina.hamrouni@talan.tn":     "+216 20 300 002",
    "khalil.mansouri@talan.tn":   "+216 20 300 003",
    "sarra.benfredj@talan.tn":    "+216 20 300 004",
    "seif.tlili@talan.tn":        "+216 20 300 005",
    "yasmine.baccar@talan.tn":    "+216 20 300 006",
    "olfa.kchok@talan.tn":        "+216 20 300 007",
    "riadh.louati@talan.tn":      "+216 20 300 008",
    "hatem.brahem@talan.tn":      "+216 20 300 009",
    "zied.haddad@talan.tn":       "+216 20 300 010",
    "hamza.chaker@talan.tn":      "+216 20 300 011",
    "mouna.sfaxi@talan.tn":       "+216 20 300 012",
    # Consultants Innovation Factory
    "eyaouniessect@gmail.com":    "+216 20 400 001",
    "yassine.cherif@talan.tn":    "+216 20 400 002",
    "nour.hamdi@talan.tn":        "+216 20 400 003",
    "bilel.saad@talan.tn":        "+216 20 400 004",
    "rim.boughanmi@talan.tn":     "+216 20 400 005",
    "oussama.khediri@talan.tn":   "+216 20 400 006",
    "asma.belhaj@talan.tn":       "+216 20 400 007",
    "ahmed2.bensalah@talan.tn":   "+216 20 400 008",
    # Salesforce
    "mariem.karray@talan.tn":     "+216 20 400 009",
    "tarek.slimani@talan.tn":     "+216 20 400 010",
    "anis.melliti@talan.tn":      "+216 20 400 011",
    "ghofrane.ayadi@talan.tn":    "+216 20 400 012",
    "nour2.hamdi@talan.tn":       "+216 20 400 013",
    # Data
    "firas.guesmi@talan.tn":      "+216 20 400 014",
    "amira.triki@talan.tn":       "+216 20 400 015",
    "rania.chouchane@talan.tn":   "+216 20 400 016",
    "hichem.dhouib@talan.tn":     "+216 20 400 017",
    "mohamed2.gharbi@talan.tn":   "+216 20 400 018",
    # Digital Factory
    "malek.hamza@talan.tn":       "+216 20 400 019",
    "sami.bouri@talan.tn":        "+216 20 400 020",
    "houda.benyoussef@talan.tn":  "+216 20 400 021",
    "nizar.jaziri@talan.tn":      "+216 20 400 022",
    # Testing
    "amel.smiri@talan.tn":        "+216 20 400 023",
    "jihen.chaari@talan.tn":      "+216 20 400 024",
    "hela.fersi@talan.tn":        "+216 20 400 025",
    "montassar.zribi@talan.tn":   "+216 20 400 026",
    # Cloud
    "achref.mejri@talan.tn":      "+216 20 400 027",
    "maroua.zahouani@talan.tn":   "+216 20 400 028",
    "lotfi.bennasr@talan.tn":     "+216 20 400 029",
    "cyrine.ferchichi@talan.tn":  "+216 20 400 030",
    "imen.zouaghi@talan.tn":      "+216 20 400 031",
    # ServiceNow
    "aymen.tlili@talan.tn":       "+216 20 400 032",
    "chaima.bougzala@talan.tn":   "+216 20 400 033",
    "walid.benhadj@talan.tn":     "+216 20 400 034",
    "samia.miled@talan.tn":       "+216 20 400 035",
    "chaima2.bougzala@talan.tn":  "+216 20 400 036",
}

# ─────────────────────────────────────────────────────────
# RH (admin, pas de profil Employee)
# ─────────────────────────────────────────────────────────
RH_USER = ("Ons RH", "ons.rh.talan@gmail.com", "rh")


# ─────────────────────────────────────────────────────────
# Seed principal
# ─────────────────────────────────────────────────────────

async def seed():
    async with AsyncSessionLocal() as db:

        # ── 0. Nettoyage + reset des séquences ───────────
        # TRUNCATE ... RESTART IDENTITY remet les auto-increment à 1
        print("Nettoyage des données existantes...")
        await db.execute(text("UPDATE hris.teams SET manager_id = NULL"))
        await db.execute(text("TRUNCATE hris.leave_logs        RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.leaves            RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.calendar_event_logs RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.calendar_events   RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.employee_skills   RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.skills            RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE crm.assignments        RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.employees         RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.teams             RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE hris.departments       RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE messages               RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE conversations          RESTART IDENTITY CASCADE"))
        await db.execute(text("TRUNCATE users                  RESTART IDENTITY CASCADE"))
        await db.commit()

        # ── 1. Utilisateur RH ─────────────────────────────
        print("👤 Création du compte RH...")
        rh_name, rh_email, rh_role = RH_USER
        rh_user = User(name=rh_name, email=rh_email, password=DEFAULT_PASSWORD, role=rh_role)
        db.add(rh_user)
        await db.flush()

        # ── 2. Départements ───────────────────────────────
        print("🏢 Création des 7 départements...")
        dept_map: dict[DepartmentEnum, Department] = {}
        for dept_enum in DEPARTMENTS:
            dept = Department(name=dept_enum)
            db.add(dept)
            await db.flush()
            dept_map[dept_enum] = dept

        # ── 3. Teams (sans manager pour l'instant) ────────
        total_teams = sum(len(names) for names in TEAM_NAMES.values())
        print(f"👥 Création des {total_teams} équipes...")
        team_map: dict[DepartmentEnum, list[Team]] = {}
        for dept_enum in DEPARTMENTS:
            dept_teams: list[Team] = []
            for team_name in TEAM_NAMES[dept_enum]:
                team = Team(
                    name=team_name,
                    department_id=dept_map[dept_enum].id,
                    manager_id=None,
                )
                db.add(team)
                await db.flush()
                dept_teams.append(team)
            team_map[dept_enum] = dept_teams

        # Dictionnaire email → Employee (pour lier les skills après)
        emp_by_email: dict[str, Employee] = {}

        # ── 4a. Directeur Général — Behjet Boussofara ────────
        print("👔 Création du Directeur Général (Behjet Boussofara)...")
        dir_name, dir_email, dir_title, dir_seniority, dir_hire, dir_dept = DIRECTOR
        dir_user = User(name=dir_name, email=dir_email, password=DEFAULT_PASSWORD, role="pm")
        db.add(dir_user)
        await db.flush()

        dir_emp = Employee(
            user_id=dir_user.id,
            team_id=team_map[dir_dept][0].id,
            manager_id=None,  # top-level, pas de manager au-dessus
            job_title=dir_title,
            seniority=dir_seniority,
            hire_date=dir_hire,
            leave_balance=22,
            phone=PHONES_MAP.get(dir_email),
        )
        db.add(dir_emp)
        await db.flush()
        emp_by_email[dir_email] = dir_emp

        # ── 4b. Users + Employees Managers ────────────────
        print("🧑‍💼 Création des managers (6 depts hors IF)...")
        manager_emp_map: dict[DepartmentEnum, Employee] = {}
        for name, email, job_title, seniority, hire_date, dept, *_ in MANAGERS:
            user = User(name=name, email=email, password=DEFAULT_PASSWORD, role="pm")
            db.add(user)
            await db.flush()

            primary_team = team_map[dept][0]
            emp = Employee(
                user_id=user.id,
                team_id=primary_team.id,
                job_title=job_title,
                seniority=seniority,
                hire_date=hire_date,
                leave_balance=22,
                manager_id=dir_emp.id,  # tous les managers → Behjet
                phone=PHONES_MAP.get(email),
            )
            db.add(emp)
            await db.flush()
            manager_emp_map[dept] = emp
            emp_by_email[email] = emp
        await db.flush()

        # ── 4c. Lead Innovation Factory — Imen Ayari ──────
        print("🌟 Création du Lead Innovation Factory (Imen Ayari)...")
        lead_name, lead_email, lead_title, lead_seniority, lead_hire, lead_dept = INNOVATION_LEAD
        lead_user = User(name=lead_name, email=lead_email, password=DEFAULT_PASSWORD, role="pm")
        db.add(lead_user)
        await db.flush()

        lead_emp = Employee(
            user_id=lead_user.id,
            team_id=team_map[lead_dept][0].id,
            manager_id=dir_emp.id,  # Imen → Behjet
            job_title=lead_title,
            seniority=lead_seniority,
            hire_date=lead_hire,
            leave_balance=22,
            phone=PHONES_MAP.get(lead_email),
        )
        db.add(lead_emp)
        await db.flush()
        emp_by_email[lead_email] = lead_emp

        # Imen Ayari est la seule responsable d'Innovation Factory
        manager_emp_map[DepartmentEnum.INNOVATION_FACTORY] = lead_emp

        # ── 5. Team Leads (1 par team, manager = Dept Head) ──
        print(f"👥 Création des Team Leads ({len(TEAM_LEADS)})...")
        # team_lead_map : team_name → Employee
        team_lead_map: dict[str, Employee] = {}

        # IF : Imen Ayari = seul team lead (déjà créée)
        team_lead_map["Innovation Factory"] = lead_emp
        team_map[DepartmentEnum.INNOVATION_FACTORY][0].manager_id = lead_emp.id

        for name, email, job_title, seniority, hire_date, dept, team_name, *_ in TEAM_LEADS:
            user = User(name=name, email=email, password=DEFAULT_PASSWORD, role="pm")
            db.add(user)
            await db.flush()

            # Trouver la team exacte par nom
            target_team = next(t for t in team_map[dept] if t.name == team_name)

            tl_emp = Employee(
                user_id=user.id,
                team_id=target_team.id,
                manager_id=manager_emp_map[dept].id,  # Team Lead → Dept Head
                job_title=job_title,
                seniority=seniority,
                hire_date=hire_date,
                leave_balance=22,
                phone=PHONES_MAP.get(email),
            )
            db.add(tl_emp)
            await db.flush()

            # La team pointe vers son Team Lead
            target_team.manager_id = tl_emp.id
            team_lead_map[team_name] = tl_emp
            emp_by_email[email] = tl_emp

        await db.flush()

        # ── 6. Créer toutes les Skills uniques ────────────
        print("🛠️  Création des compétences...")
        all_skill_names: set[str] = set()
        # Consultants
        for *_, skills in CONSULTANTS:
            for s in skills.split(","):
                all_skill_names.add(s.strip())
        # Managers, Leads, Heads, Directeur (via SKILLS_MAP)
        for skills_str in SKILLS_MAP.values():
            for s in skills_str.split(","):
                all_skill_names.add(s.strip())

        skill_map: dict[str, Skill] = {}
        for skill_name in sorted(all_skill_names):
            skill = Skill(name=skill_name)
            db.add(skill)
            await db.flush()
            skill_map[skill_name] = skill

        # Correspondance séniorité → niveau de compétence
        SENIORITY_TO_LEVEL = {
            SeniorityEnum.JUNIOR:    SkillLevelEnum.BEGINNER,
            SeniorityEnum.MID:       SkillLevelEnum.INTERMEDIATE,
            SeniorityEnum.SENIOR:    SkillLevelEnum.ADVANCED,
            SeniorityEnum.LEAD:      SkillLevelEnum.EXPERT,
            SeniorityEnum.HEAD:      SkillLevelEnum.EXPERT,
            SeniorityEnum.PRINCIPAL: SkillLevelEnum.EXPERT,
        }

        # ── 6b. Lier les skills des managers/leads/heads/directeur ──
        print("🔗 Liaison skills → managers, leads, heads, directeur...")
        for email, skills_str in SKILLS_MAP.items():
            emp = emp_by_email.get(email)
            if not emp:
                continue
            level = SENIORITY_TO_LEVEL.get(emp.seniority, SkillLevelEnum.EXPERT)
            for skill_name in skills_str.split(","):
                skill_name = skill_name.strip()
                if skill_name in skill_map:
                    db.add(EmployeeSkill(
                        employee_id=emp.id,
                        skill_id=skill_map[skill_name].id,
                        level=level,
                    ))
        await db.flush()

        # ── 7. Users + Employees Consultants ─────────────
        # Chaque consultant → assigné à une team → manager = Team Lead de cette team
        print(f"👩‍💻 Création des consultants ({len(CONSULTANTS)})...")
        dept_team_index: dict[DepartmentEnum, int] = {dept: 0 for dept in DEPARTMENTS}
        for name, email, job_title, seniority, hire_date, dept, skills in CONSULTANTS:
            user = User(name=name, email=email, password=DEFAULT_PASSWORD, role="consultant")
            db.add(user)
            await db.flush()

            teams_for_dept = team_map[dept]
            selected_team = teams_for_dept[dept_team_index[dept] % len(teams_for_dept)]
            dept_team_index[dept] += 1

            emp = Employee(
                user_id=user.id,
                team_id=selected_team.id,
                manager_id=selected_team.manager_id,  # = Team Lead de cette team
                job_title=job_title,
                seniority=seniority,
                hire_date=hire_date,
                leave_balance=22,
                phone=PHONES_MAP.get(email),
            )
            db.add(emp)
            await db.flush()

            # Lier les compétences
            level = SENIORITY_TO_LEVEL[seniority]
            for skill_name in skills.split(","):
                skill_name = skill_name.strip()
                db.add(EmployeeSkill(
                    employee_id=emp.id,
                    skill_id=skill_map[skill_name].id,
                    level=level,
                ))

        await db.commit()

        # ── Résumé ────────────────────────────────────────
        by_dept = {}
        for _, _, _, _, _, dept, *_ in CONSULTANTS:
            by_dept[dept] = by_dept.get(dept, 0) + 1

        print("\n" + "═" * 55)
        print("✅ Seed terminé !")
        print("═" * 55)
        print(f"  1  Directeur Général  : {DIRECTOR[0]}")
        print(f"  6  Dept Heads (pm)    : tous → {DIRECTOR[0]}")
        print(f"  1  Head IF + TL       : {INNOVATION_LEAD[0]} → {DIRECTOR[0]}")
        print(f"  {len(TEAM_LEADS)} Team Leads (pm)   : 2 par dept hors IF → leur Dept Head")
        print(f"  1  utilisateur RH     : {RH_USER[1]}")
        print(f"  {total_teams} équipes             : chaque team → son Team Lead")
        print(f"  {len(CONSULTANTS)} consultants        :")
        for dept in DEPARTMENTS:
            print(f"     {dept.value:25} {by_dept.get(dept, 0)} consultants")
        print(f"\n  Total employés     : {1 + 1 + len(DEPT_HEADS) + len(TEAM_LEADS) + len(CONSULTANTS)}")
        print(f"  Mot de passe       : Talan2026!")
        print("═" * 55)


asyncio.run(seed())
