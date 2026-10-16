from pathlib import Path

from app.operations.config_validation import validate_project_config


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    problems = validate_project_config(root)
    if problems:
        print("Project configuration validation failed:")
        for problem in problems:
            print(f"- {problem}")
        raise SystemExit(1)
    print("Project configuration validation passed.")
