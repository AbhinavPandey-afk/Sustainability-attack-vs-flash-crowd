from experiments.run_experiment import git_commit


def test_git_commit_returns_a_real_commit_hash_or_unknown():
    commit = git_commit()
    assert commit == "unknown" or len(commit) == 40  # full SHA-1 hex length
