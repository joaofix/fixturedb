#!/usr/bin/env python3
"""Inspect extracted human fixtures: save raw source and diffs for each fixture.

Writes outputs to `output/human-fixture-inspection/<language>/` with one file
per fixture containing metadata, the raw source lines, and the git diff for the
commit that added the fixture.
"""

import csv
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLONES = ROOT / "clones"
FIX_DIR = ROOT / "fixtures-from-humans"
OUT = ROOT / "output" / "human-fixture-inspection"
OUT.mkdir(parents=True, exist_ok=True)

csv_paths = sorted(FIX_DIR.glob("*_human_fixtures.csv"))
if not csv_paths:
    print("No fixture CSVs found in", FIX_DIR)
    raise SystemExit(1)

count = 0
errors = []

for csv_path in csv_paths:
    lang = csv_path.name.split("_")[0]
    out_lang = OUT / lang
    out_lang.mkdir(parents=True, exist_ok=True)

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            count += 1
            repo = (row.get("repo_name") or "").strip()
            commit = (row.get("commit_sha") or "").strip()
            file_path = (row.get("file_path") or "").strip()
            start_line = int(row.get("start_line") or 0)
            end_line = int(row.get("end_line") or 0)
            fixture_name = (row.get("fixture_name") or "").strip()

            if not repo or not commit or not file_path:
                errors.append((repo, commit, file_path, "missing fields"))
                continue

            repo_dir = CLONES / repo.replace("/", "__")
            if not repo_dir.exists():
                errors.append((repo, commit, file_path, "repo not cloned"))
                continue

            # safe filename
            safe_repo = repo.replace("/", "__")
            safe_name = (
                re.sub(r"[^A-Za-z0-9_.-]", "_", fixture_name)[:80] or f"fixture_{i}"
            )
            out_file = out_lang / f"{safe_repo}__{commit[:8]}__{safe_name}__.txt"

            try:
                # get file content at commit
                p = subprocess.run(
                    ["git", "show", f"{commit}:{file_path}"],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                file_content = p.stdout if p.returncode == 0 else None

                # get diff for commit limited to file
                q = subprocess.run(
                    ["git", "show", "--unified=3", commit, "--", file_path],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                diff_text = q.stdout if q.returncode == 0 else None

                # extract snippet from file_content
                snippet = ""
                if file_content:
                    lines = file_content.splitlines()
                    # guard indices
                    s = max(1, start_line)
                    e = min(len(lines), end_line) if end_line >= s else s
                    # convert 1-based to 0-based
                    snippet = "\n".join(lines[s - 1 : e])

                meta = {
                    "repo": repo,
                    "commit": commit,
                    "file_path": file_path,
                    "fixture_name": fixture_name,
                    "start_line": start_line,
                    "end_line": end_line,
                }

                with out_file.open("w", encoding="utf-8") as ofh:
                    ofh.write("METADATA:\n")
                    json.dump(meta, ofh, indent=2, ensure_ascii=False)
                    ofh.write("\n\n")
                    ofh.write("SNIPPET (requested lines):\n")
                    ofh.write(snippet or "[no snippet available]")
                    ofh.write("\n\n")
                    ofh.write("FULL FILE AT COMMIT:\n")
                    ofh.write(file_content or "[file unavailable at commit]")
                    ofh.write("\n\n")
                    ofh.write("GIT DIFF FOR COMMIT (file scope):\n")
                    ofh.write(diff_text or "[diff unavailable]")

            except Exception as exc:
                errors.append((repo, commit, file_path, str(exc)))

print(f"Wrote inspection files for {count} fixtures to {OUT} (errors: {len(errors)})")
if errors:
    print("Sample errors:")
    for e in errors[:20]:
        print(e)
