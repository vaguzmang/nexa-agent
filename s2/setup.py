import json

from .storage import ensure_database, default_db_path
from .tools import list_teaching_strategies


def main():
    path = default_db_path()
    ensure_database(path)
    strategies = list_teaching_strategies("misconception", db_path=path)
    print(f"NEXA S2 SQLite listo: {path}")
    print(
        json.dumps(
            {
                "database": str(path),
                "sample_catalog_count": len(strategies.get("eligible", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
