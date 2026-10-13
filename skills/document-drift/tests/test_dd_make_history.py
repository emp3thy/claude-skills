from dd_common import run_git
from dd_helpers import make_repo


def test_rename_key_produces_a_git_rename(tmp_path):
    repo = make_repo(tmp_path, [
        {"author": "A <a@x>", "date": "2024-01-01T00:00:00+00:00", "subject": "add",
         "files": {"src/old.py": "x = 1\n"}},
        {"author": "A <a@x>", "date": "2024-02-01T00:00:00+00:00", "subject": "mv",
         "rename": {"src/old.py": "src/new.py"}},
    ])
    log = run_git(repo, ["log", "-M", "--diff-filter=R", "--name-status", "--format="])
    assert "src/old.py\tsrc/new.py" in log
