import asyncio
import os
import sys
from typing import Any

from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal


CHECKS = [
    {
        "name": "Employees without manager",
        "query": """
            SELECT e.id, u.name, u.email
            FROM hris.employees e
            JOIN users u ON u.id = e.user_id
            WHERE e.manager_id IS NULL
            ORDER BY e.id
        """,
    },
    {
        "name": "Teams without manager",
        "query": """
            SELECT t.id, t.name, d.name AS department
            FROM hris.teams t
            LEFT JOIN hris.departments d ON d.id = t.department_id
            WHERE t.manager_id IS NULL
            ORDER BY t.id
        """,
    },
    {
        "name": "Consultant/PM users without employee profile",
        "query": """
            SELECT u.id, u.name, u.email, u.role
            FROM users u
            LEFT JOIN hris.employees e ON e.user_id = u.id
            WHERE u.role IN ('consultant', 'pm')
              AND e.id IS NULL
            ORDER BY u.id
        """,
    },
    {
        "name": "Employees with manager in another department",
        "query": """
            SELECT
                e.id AS employee_id,
                ue.name AS employee_name,
                m.id AS manager_employee_id,
                um.name AS manager_name,
                td_e.name AS employee_department,
                td_m.name AS manager_department
            FROM hris.employees e
            JOIN users ue ON ue.id = e.user_id
            JOIN hris.teams te ON te.id = e.team_id
            JOIN hris.departments td_e ON td_e.id = te.department_id
            JOIN hris.employees m ON m.id = e.manager_id
            JOIN users um ON um.id = m.user_id
            JOIN hris.teams tm ON tm.id = m.team_id
            JOIN hris.departments td_m ON td_m.id = tm.department_id
            WHERE td_e.id <> td_m.id
            ORDER BY e.id
        """,
    },
]


SUMMARY_QUERIES = [
    {
        "title": "Employees by department",
        "query": """
            SELECT d.name AS department, COUNT(e.id) AS employee_count
            FROM hris.departments d
            LEFT JOIN hris.teams t ON t.department_id = d.id
            LEFT JOIN hris.employees e ON e.team_id = t.id
            GROUP BY d.name
            ORDER BY d.name
        """,
    },
    {
        "title": "Employees by team",
        "query": """
            SELECT t.name AS team, d.name AS department, COUNT(e.id) AS employee_count
            FROM hris.teams t
            LEFT JOIN hris.departments d ON d.id = t.department_id
            LEFT JOIN hris.employees e ON e.team_id = t.id
            GROUP BY t.name, d.name
            ORDER BY d.name, t.name
        """,
    },
    {
        "title": "Duplicate employee names",
        "query": """
            SELECT u.name, COUNT(*) AS occurrences
            FROM users u
            JOIN hris.employees e ON e.user_id = u.id
            GROUP BY u.name
            HAVING COUNT(*) > 1
            ORDER BY occurrences DESC, u.name
        """,
    },
]


def format_rows(rows: list[dict[str, Any]], max_rows: int = 20) -> str:
    if not rows:
        return "  (none)"

    headers = list(rows[0].keys())
    widths = {h: len(h) for h in headers}
    visible_rows = rows[:max_rows]

    for row in visible_rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row[h])))

    sep = "  "
    header_line = sep.join(h.ljust(widths[h]) for h in headers)
    dash_line = sep.join("-" * widths[h] for h in headers)
    data_lines = [sep.join(str(row[h]).ljust(widths[h]) for h in headers) for row in visible_rows]

    suffix = ""
    if len(rows) > max_rows:
        suffix = f"\n  ... and {len(rows) - max_rows} more rows"

    return "\n".join([f"  {header_line}", f"  {dash_line}"] + [f"  {line}" for line in data_lines]) + suffix


async def fetch_rows(db, query: str) -> list[dict[str, Any]]:
    result = await db.execute(text(query))
    return [dict(row) for row in result.mappings().all()]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        print("=" * 70)
        print("DB Coherence Report")
        print("=" * 70)

        total_issues = 0

        for check in CHECKS:
            rows = await fetch_rows(db, check["query"])
            issue_count = len(rows)
            total_issues += issue_count

            status = "OK" if issue_count == 0 else "ISSUES"
            print(f"\n[{status}] {check['name']} -> {issue_count}")
            if issue_count:
                print(format_rows(rows))

        print("\n" + "-" * 70)
        print("Summary")
        print("-" * 70)

        for summary in SUMMARY_QUERIES:
            rows = await fetch_rows(db, summary["query"])
            print(f"\n{summary['title']}")
            print(format_rows(rows, max_rows=200))

        print("\n" + "=" * 70)
        if total_issues == 0:
            print("RESULT: No coherence issue detected.")
        else:
            print(f"RESULT: {total_issues} issue(s) detected. Review sections marked ISSUES.")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
