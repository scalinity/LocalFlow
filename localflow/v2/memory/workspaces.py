"""Read local Git identity for explicitly approved roots, without network access."""

from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


def remote_identity(value):
    """Keep repository identity, never URL credentials, options or local paths."""
    if not value or len(value) > 2000 or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    if '://' in value:
        try:
            parsed = urlsplit(value)
            host = parsed.hostname
        except ValueError:
            return None
        if parsed.scheme not in ('https', 'http', 'ssh', 'git') or not host:
            return None
        host, path = host.lower(), parsed.path
    else:
        match = re.fullmatch(r'(?:[^/@:]+@)?([A-Za-z0-9.-]+):([^?#]+)', value)
        if not match:
            return None
        host, path = match.group(1).lower(), match.group(2)
    path = path.strip('/').removesuffix('.git')
    return f'{host}/{path}' if path and not path.startswith(('-', ':')) else None


def read_workspace(root):
    """Run only bounded read-only Git commands; callers use a background job."""
    def git(*args):
        result = subprocess.run(['/usr/bin/git', '-c', 'core.fsmonitor=false', '-C', str(root), *args],
            capture_output=True, text=True, timeout=1, check=False)
        return result.stdout.strip() if result.returncode == 0 and len(result.stdout) <= 4000 else ''
    try:
        root = Path(root).resolve(strict=True)
        top = git('rev-parse', '--show-toplevel')
        if not top:
            return None
        return {'root': str(root), 'repository_root': str(Path(top).resolve(strict=True)),
                'remote': remote_identity(git('config', '--local', '--get', 'remote.origin.url')),
                'head': git('rev-parse', '--verify', 'HEAD') or None}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
