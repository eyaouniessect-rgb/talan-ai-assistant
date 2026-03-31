# scripts/seed_employees.py
# ═══════════════════════════════════════════════════════════
# Seed Talan Tunisie — 50 employés répartis sur 7 départements
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
    DepartmentEnum.INNOVATION_FACTORY: "Innovation Factory",
    DepartmentEnum.SALESFORCE:         "Salesforce",
    DepartmentEnum.DATA:               "Data & Analytics",
    DepartmentEnum.DIGITAL_FACTORY:    "Digital Factory",
    DepartmentEnum.TESTING:            "Testing",
    DepartmentEnum.CLOUD:              "Cloud",
    DepartmentEnum.SERVICE_NOW:        "ServiceNow",
}

# ─────────────────────────────────────────────────────────
# Managers — 7 (1 par département)
# role="pm"
# ─────────────────────────────────────────────────────────
# (name, email, job_title, seniority, hire_date, dept)

MANAGERS = [
    ("Ahmed Ben Salah",  "ahmed.bensalah@talan.tn",  "Engineering Manager",    SeniorityEnum.PRINCIPAL, date(2018, 3,  1),  DepartmentEnum.INNOVATION_FACTORY),
    ("Sana Trabelsi",    "sana.trabelsi@talan.tn",   "Salesforce Lead",        SeniorityEnum.LEAD,      date(2019, 6, 15),  DepartmentEnum.SALESFORCE),
    ("Mohamed Gharbi",   "mohamed.gharbi@talan.tn",  "Data Engineering Lead",  SeniorityEnum.PRINCIPAL, date(2017, 9,  1),  DepartmentEnum.DATA),
    ("Ines Jebali",      "ines.jebali@talan.tn",     "Digital Factory Manager",SeniorityEnum.LEAD,      date(2020, 1, 10),  DepartmentEnum.DIGITAL_FACTORY),
    ("Karim Mzoughi",    "karim.mzoughi@talan.tn",   "QA Lead",                SeniorityEnum.LEAD,      date(2019, 4, 20),  DepartmentEnum.TESTING),
    ("Walid Karray",     "walid.karray@talan.tn",    "Cloud Architect Lead",   SeniorityEnum.PRINCIPAL, date(2018, 8,  5),  DepartmentEnum.CLOUD),
    ("Fatma Boubaker",   "fatma.boubaker@talan.tn",  "ServiceNow Manager",     SeniorityEnum.PRINCIPAL, date(2018, 11, 5),  DepartmentEnum.SERVICE_NOW),
]

# ─────────────────────────────────────────────────────────
# Consultants — 43 (50 - 7 managers)
# (name, email, job_title, seniority, hire_date, dept, skills)
# ─────────────────────────────────────────────────────────

CONSULTANTS = [
    # ── Innovation Factory (6) ─────────────────────────
    ("Yassine Cherif",    "yassine.cherif@talan.tn",    "Full Stack Developer",     SeniorityEnum.SENIOR, date(2021, 2,  1),  DepartmentEnum.INNOVATION_FACTORY, "React, Node.js, PostgreSQL"),
    ("Nour Hamdi",        "nour.hamdi@talan.tn",         "Software Architect",       SeniorityEnum.SENIOR, date(2020, 7, 15),  DepartmentEnum.INNOVATION_FACTORY, "Java, Microservices, Kafka"),
    ("Bilel Saad",        "bilel.saad@talan.tn",         "Backend Developer",        SeniorityEnum.MID,    date(2022, 3,  1),  DepartmentEnum.INNOVATION_FACTORY, "Python, FastAPI, Redis"),
    ("Rim Boughanmi",     "rim.boughanmi@talan.tn",      "Frontend Developer",       SeniorityEnum.MID,    date(2022, 6, 10),  DepartmentEnum.INNOVATION_FACTORY, "Vue.js, TypeScript, CSS"),
    ("Oussama Khediri",   "oussama.khediri@talan.tn",    "Software Engineer",        SeniorityEnum.JUNIOR, date(2024, 1, 15),  DepartmentEnum.INNOVATION_FACTORY, "Java, Spring Boot"),
    ("Asma Belhaj",       "asma.belhaj@talan.tn",        "Full Stack Developer",     SeniorityEnum.JUNIOR, date(2024, 9,  1),  DepartmentEnum.INNOVATION_FACTORY, "React, Python, Docker"),

    # ── Salesforce (6) ────────────────────────────────
    ("Mariem Karray",     "mariem.karray@talan.tn",      "Salesforce Developer",     SeniorityEnum.SENIOR, date(2020, 3,  1),  DepartmentEnum.SALESFORCE, "Apex, LWC, SOQL"),
    ("Tarek Slimani",     "tarek.slimani@talan.tn",      "Salesforce Admin",         SeniorityEnum.MID,    date(2021, 8, 15),  DepartmentEnum.SALESFORCE, "Salesforce Admin, Flows"),
    ("Lina Hamrouni",     "lina.hamrouni@talan.tn",      "CRM Consultant",           SeniorityEnum.SENIOR, date(2019, 5,  1),  DepartmentEnum.SALESFORCE, "Salesforce, CRM, Vlocity"),
    ("Anis Melliti",      "anis.melliti@talan.tn",       "Salesforce Developer",     SeniorityEnum.MID,    date(2022, 1, 10),  DepartmentEnum.SALESFORCE, "Apex, Triggers, Integration"),
    ("Ghofrane Ayadi",    "ghofrane.ayadi@talan.tn",     "Salesforce Consultant",    SeniorityEnum.JUNIOR, date(2024, 3,  1),  DepartmentEnum.SALESFORCE, "Salesforce, Flows"),
    ("Wael Ben Amor",     "wael.benamor@talan.tn",       "Salesforce Architect",     SeniorityEnum.LEAD,   date(2018, 7,  1),  DepartmentEnum.SALESFORCE, "Salesforce, MuleSoft, Architecture"),

    # ── Data & Analytics (6) ──────────────────────────
    ("Khalil Mansouri",   "khalil.mansouri@talan.tn",    "Data Engineer",            SeniorityEnum.SENIOR, date(2020, 4,  1),  DepartmentEnum.DATA, "Spark, Python, Airflow"),
    ("Sarra Ben Fredj",   "sarra.benfredj@talan.tn",     "Data Scientist",           SeniorityEnum.SENIOR, date(2021, 1, 15),  DepartmentEnum.DATA, "Python, ML, TensorFlow"),
    ("Firas Guesmi",      "firas.guesmi@talan.tn",       "ML Engineer",              SeniorityEnum.MID,    date(2022, 5,  1),  DepartmentEnum.DATA, "PyTorch, MLflow, Azure ML"),
    ("Amira Triki",       "amira.triki@talan.tn",        "Data Analyst",             SeniorityEnum.MID,    date(2022, 9,  1),  DepartmentEnum.DATA, "SQL, Power BI, Python"),
    ("Hichem Dhouib",     "hichem.dhouib@talan.tn",      "Data Engineer",            SeniorityEnum.JUNIOR, date(2024, 2,  1),  DepartmentEnum.DATA, "Python, dbt, Snowflake"),
    ("Rania Chouchane",   "rania.chouchane@talan.tn",    "Data Scientist",           SeniorityEnum.MID,    date(2023, 3, 15),  DepartmentEnum.DATA, "Python, NLP, Scikit-learn"),

    # ── Digital Factory (6) ───────────────────────────
    ("Seif Tlili",        "seif.tlili@talan.tn",         "Frontend Developer",       SeniorityEnum.SENIOR, date(2020, 2,  1),  DepartmentEnum.DIGITAL_FACTORY, "React, Next.js, Tailwind"),
    ("Yasmine Baccar",    "yasmine.baccar@talan.tn",      "UX/UI Designer",           SeniorityEnum.SENIOR, date(2019, 8,  1),  DepartmentEnum.DIGITAL_FACTORY, "Figma, UX Research, Design System"),
    ("Malek Hamza",       "malek.hamza@talan.tn",         "Mobile Developer",         SeniorityEnum.MID,    date(2022, 4,  1),  DepartmentEnum.DIGITAL_FACTORY, "Flutter, React Native"),
    ("Sami Bouri",        "sami.bouri@talan.tn",          "Backend Developer",        SeniorityEnum.MID,    date(2022, 8,  1),  DepartmentEnum.DIGITAL_FACTORY, "Node.js, Express, MongoDB"),
    ("Houda Ben Youssef", "houda.benyoussef@talan.tn",    "Full Stack Developer",     SeniorityEnum.MID,    date(2023, 1, 10),  DepartmentEnum.DIGITAL_FACTORY, "Angular, .NET, SQL Server"),
    ("Nizar Jaziri",      "nizar.jaziri@talan.tn",        "Frontend Developer",       SeniorityEnum.JUNIOR, date(2024, 9,  1),  DepartmentEnum.DIGITAL_FACTORY, "React, CSS, JavaScript"),

    # ── Testing (6) ───────────────────────────────────
    ("Amel Smiri",        "amel.smiri@talan.tn",          "QA Engineer",              SeniorityEnum.SENIOR, date(2020, 6,  1),  DepartmentEnum.TESTING, "Selenium, Cypress, JIRA"),
    ("Riadh Louati",      "riadh.louati@talan.tn",        "Test Automation Engineer", SeniorityEnum.SENIOR, date(2019, 10, 1),  DepartmentEnum.TESTING, "Robot Framework, Python, API Testing"),
    ("Jihen Chaari",      "jihen.chaari@talan.tn",        "Performance Tester",       SeniorityEnum.MID,    date(2022, 2,  1),  DepartmentEnum.TESTING, "JMeter, Gatling, K6"),
    ("Hela Fersi",        "hela.fersi@talan.tn",          "QA Engineer",              SeniorityEnum.JUNIOR, date(2024, 4,  1),  DepartmentEnum.TESTING, "Cypress, Postman, JIRA"),
    ("Montassar Zribi",   "montassar.zribi@talan.tn",     "Test Automation Engineer", SeniorityEnum.MID,    date(2023, 5,  1),  DepartmentEnum.TESTING, "Playwright, Selenium, Python"),
    ("Olfa Kchok",        "olfa.kchok@talan.tn",          "QA Lead",                  SeniorityEnum.LEAD,   date(2018, 9,  1),  DepartmentEnum.TESTING, "Test Strategy, Cypress, JIRA"),

    # ── Cloud (7) ─────────────────────────────────────
    ("Achref Mejri",      "achref.mejri@talan.tn",        "Cloud Engineer",           SeniorityEnum.MID,    date(2022, 7,  1),  DepartmentEnum.CLOUD, "AWS, GCP, Terraform"),
    ("Lotfi Ben Nasr",    "lotfi.bennasr@talan.tn",       "DevSecOps Engineer",       SeniorityEnum.SENIOR, date(2020, 1, 15),  DepartmentEnum.CLOUD, "Docker, Kubernetes, Security"),
    ("Maroua Zahouani",   "maroua.zahouani@talan.tn",     "Cloud Infrastructure Eng", SeniorityEnum.MID,    date(2022, 11, 1),  DepartmentEnum.CLOUD, "Azure, Terraform, Ansible"),
    ("Cyrine Ferchichi",  "cyrine.ferchichi@talan.tn",    "DevOps Engineer",          SeniorityEnum.MID,    date(2023, 5,  1),  DepartmentEnum.CLOUD, "Docker, CI/CD, Jenkins"),
    ("Hatem Brahem",      "hatem.brahem@talan.tn",        "SRE Engineer",             SeniorityEnum.SENIOR, date(2020, 9,  1),  DepartmentEnum.CLOUD, "Go, Prometheus, Grafana"),
    ("Zied Haddad",       "zied.haddad@talan.tn",         "Cloud Data Engineer",      SeniorityEnum.SENIOR, date(2020, 11, 1),  DepartmentEnum.CLOUD, "Kafka, GCP, Spark"),
    ("Imen Zouaghi",      "imen.zouaghi@talan.tn",        "Cloud Engineer",           SeniorityEnum.JUNIOR, date(2024, 6,  1),  DepartmentEnum.CLOUD, "AWS, Python, Terraform"),

    # ── ServiceNow (6) ────────────────────────────────
    ("Hamza Chaker",      "hamza.chaker@talan.tn",        "ServiceNow Developer",     SeniorityEnum.SENIOR, date(2020, 8,  1),  DepartmentEnum.SERVICE_NOW, "ServiceNow, JavaScript, Glide"),
    ("Mouna Sfaxi",       "mouna.sfaxi@talan.tn",         "ITSM Consultant",          SeniorityEnum.SENIOR, date(2019, 3,  1),  DepartmentEnum.SERVICE_NOW, "ITSM, ITIL, ServiceNow"),
    ("Aymen Tlili",       "aymen.tlili@talan.tn",         "ServiceNow Admin",         SeniorityEnum.MID,    date(2022, 11, 1),  DepartmentEnum.SERVICE_NOW, "ServiceNow Admin, Workflows"),
    ("Chaima Bougzala",   "chaima.bougzala@talan.tn",     "Platform Developer",       SeniorityEnum.MID,    date(2023, 2,  1),  DepartmentEnum.SERVICE_NOW, "ServiceNow, REST API, Angular"),
    ("Samia Miled",       "samia.miled@talan.tn",         "ITSM Consultant",          SeniorityEnum.MID,    date(2021, 9,  1),  DepartmentEnum.SERVICE_NOW, "ITIL, ServiceNow, Process Design"),
    ("Walid Ben Hadj",    "walid.benhadj@talan.tn",       "ServiceNow Developer",     SeniorityEnum.JUNIOR, date(2024, 7,  1),  DepartmentEnum.SERVICE_NOW, "ServiceNow, JavaScript"),
]

# ─────────────────────────────────────────────────────────
# RH (admin, pas de profil Employee)
# ─────────────────────────────────────────────────────────
RH_USER = ("Mariem Chaabane", "mariem.chaabane@talan.tn", "rh")


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
        print("👥 Création des 7 équipes...")
        team_map: dict[DepartmentEnum, Team] = {}
        for dept_enum in DEPARTMENTS:
            team = Team(
                name=TEAM_NAMES[dept_enum],
                department_id=dept_map[dept_enum].id,
                manager_id=None,
            )
            db.add(team)
            await db.flush()
            team_map[dept_enum] = team

        # ── 4. Users + Employees Managers ────────────────
        print("🧑‍💼 Création des managers (7)...")
        manager_emp_map: dict[DepartmentEnum, Employee] = {}
        for name, email, job_title, seniority, hire_date, dept in MANAGERS:
            user = User(name=name, email=email, password=DEFAULT_PASSWORD, role="pm")
            db.add(user)
            await db.flush()

            emp = Employee(
                user_id=user.id,
                team_id=team_map[dept].id,
                job_title=job_title,
                seniority=seniority,
                hire_date=hire_date,
                leave_balance=22,
            )
            db.add(emp)
            await db.flush()
            manager_emp_map[dept] = emp

        # ── 5. Mettre à jour manager_id des Teams ────────
        print("🔗 Liaison managers ↔ équipes...")
        for dept_enum, emp in manager_emp_map.items():
            team_map[dept_enum].manager_id = emp.id
        await db.flush()

        # ── 6. Créer toutes les Skills uniques ────────────
        print("🛠️  Création des compétences...")
        all_skill_names: set[str] = set()
        for *_, skills in CONSULTANTS:
            for s in skills.split(","):
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
            SeniorityEnum.PRINCIPAL: SkillLevelEnum.EXPERT,
        }

        # ── 7. Users + Employees Consultants ─────────────
        print("👩‍💻 Création des consultants (43)...")
        for name, email, job_title, seniority, hire_date, dept, skills in CONSULTANTS:
            user = User(name=name, email=email, password=DEFAULT_PASSWORD, role="consultant")
            db.add(user)
            await db.flush()

            emp = Employee(
                user_id=user.id,
                team_id=team_map[dept].id,
                manager_id=manager_emp_map[dept].id,
                job_title=job_title,
                seniority=seniority,
                hire_date=hire_date,
                leave_balance=22,
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
        print(f"  1  utilisateur RH  : {RH_USER[1]}")
        print(f"  7  managers (pm)   : 1 par département")
        print(f"  43 consultants     :")
        for dept in DEPARTMENTS:
            print(f"     {TEAM_NAMES[dept]:25} {by_dept.get(dept, 0)} consultants")
        print(f"\n  Total employés     : {len(MANAGERS) + len(CONSULTANTS)}")
        print(f"  Mot de passe       : Talan2026!")
        print("═" * 55)


asyncio.run(seed())
