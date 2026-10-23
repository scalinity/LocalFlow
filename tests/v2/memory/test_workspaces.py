from pathlib import Path
import subprocess
import tempfile
import unittest

from localflow.v2.memory.models import ContextPack, WorkspaceIdentity
from localflow.v2.memory.workspaces import read_workspace, remote_identity


class WorkspaceIdentityTests(unittest.TestCase):
    def test_remote_identity_discards_credentials_and_local_paths(self):
        self.assertEqual(remote_identity('https://login:password@example.test/team/repo.git?token=private#fragment'),
                         'example.test/team/repo')
        self.assertEqual(remote_identity('git@example.test:team/repo.git'), 'example.test/team/repo')
        for value in ('/local/repo', 'file:///local/repo', 'ext::run-command', 'https://example.test/a\nb'):
            self.assertIsNone(remote_identity(value))

    def test_real_git_worktrees_keep_separate_paths_and_shared_remote(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'repo'
            other = Path(td) / 'worktree'
            root.mkdir()
            def git(*args):
                return subprocess.run(['/usr/bin/git', '-C', str(root), *args],
                                      check=True, capture_output=True, text=True)
            git('init', '-q')
            if subprocess.run(['/usr/bin/git', 'var', 'GIT_AUTHOR_IDENT'],
                              capture_output=True).returncode:
                self.skipTest('No existing Git identity for disposable fixture commit')
            git('commit', '--allow-empty', '-qm', 'Create disposable fixture')
            git('remote', 'add', 'origin', 'git@example.test:team/project.git')
            git('worktree', 'add', '--detach', str(other), 'HEAD')
            first, second = read_workspace(root), read_workspace(other)
            self.assertNotEqual(first['root'], second['root'])
            self.assertEqual(first['remote'], second['remote'])
            self.assertEqual(first['head'], second['head'])
            pack = ContextPack('project-fixture', workspaces=(WorkspaceIdentity(**first, observed_at=123),))
            self.assertEqual(ContextPack.from_dict(pack.to_dict()), pack)
            git('remote', 'set-url', 'origin', 'https://example.test/team/changed.git')
            self.assertEqual(read_workspace(other)['remote'], 'example.test/team/changed')

    def test_non_git_root_is_not_given_a_repository_identity(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(read_workspace(td))
            self.assertIsNone(read_workspace(Path(td) / 'missing-folder'))


if __name__ == '__main__':
    unittest.main()
