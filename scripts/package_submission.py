"""Create a source archive with an explicit allowlist; never package keys or runtime data."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "artifacts" / "submission.zip"
FOLDERS = {"app", "static", "policies", "examples", "evaluation", "tests", "scripts", "docs", "System Design"}
FILES = {
    ".gitattributes",
    ".gitignore",
    ".dockerignore",
    ".env.example",
    "Dockerfile",
    "compose.yaml",
    "README.md",
    "requirements.txt",
    "requirements-tools.txt",
    "pytest.ini",
    "pyproject.toml",
    "run.ps1",
    "run.sh",
}
RESULTS = {
    "offline",
    "live-smoke",
    "gemini-diagnostic",
    "gemini-quality",
    "live-groq",
    "docker-smoke",
    "gemini-recovery",
    "gemini-recovery-final",
    "direct-answers",
}


def include(file):
    relative = file.relative_to(ROOT)
    if "__pycache__" in relative.parts or file.suffix == ".pyc":
        return False
    if len(relative.parts) == 1:
        return file.name in FILES
    if relative.parts[0] in FOLDERS:
        return True
    if relative.parts[0] == "artifacts":
        return (len(relative.parts) == 2 and file.name in {"tests.xml", "docker-tests.xml"}) or (
            len(relative.parts) == 3 and relative.parts[1] in RESULTS and file.suffix in {".json", ".jsonl"}
        )
    return False


if __name__ == "__main__":
    DESTINATION.parent.mkdir(exist_ok=True)
    # Do not traverse .venv, .git, data, original briefs, or other unapproved directories.
    candidates = [ROOT / name for name in FILES]
    for folder in sorted(FOLDERS | {"artifacts"}):
        candidates.extend((ROOT / folder).rglob("*"))
    files = sorted({f for f in candidates if f.is_file() and include(f)})
    assert not any(f.name == ".env" or ".git" in f.parts for f in files)
    with ZipFile(DESTINATION, "w", ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(ROOT).as_posix())
    with ZipFile(DESTINATION) as archive:
        assert archive.testzip() is None
    print(
        f"Created {DESTINATION.name} with {len(files)} source and evaluation files; private .env and runtime directories excluded."
    )
