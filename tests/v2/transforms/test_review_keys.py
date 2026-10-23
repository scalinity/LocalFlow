"""Physical press lifecycle, independent of training consent or UI mocks."""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.transforms.review_keys import ReviewKeyLease


def test_exactly_once_and_release_after_hide():
    events = []
    lease = ReviewKeyLease(lambda *x: events.append(x))
    lease.arm('one', 42, ready=True, enabled=True)
    assert lease.handle('down', 36, pid=42)
    assert events == [('accept', 'one')]
    assert lease.claim('one')
    assert not lease.claim('one')
    for _ in range(10):
        assert lease.handle('down', 36, repeat=True, pid=42)
    assert lease.handle('up', 36, pid=42)
    assert not lease.handle('down', 36, pid=42)


def test_generating_does_not_queue_accept():
    events = []
    lease = ReviewKeyLease(lambda *x: events.append(x))
    lease.arm('one', 42)
    assert lease.handle('down', 76, pid=42)
    lease.arm('one', 42, ready=True, enabled=True)
    assert lease.handle('down', 76, repeat=True, pid=42)
    assert events == [('working', 'one')]
    assert lease.handle('up', 76, pid=42)
    assert lease.handle('down', 76, pid=42)
    assert events[-1] == ('accept', 'one')


def test_preheld_ime_modified_and_unrelated_keys():
    events = []
    lease = ReviewKeyLease(lambda *x: events.append(x))
    assert not lease.handle('down', 36, pid=42)
    lease.arm('one', 42, ready=True, enabled=True)
    assert lease.handle('down', 36, repeat=True, pid=42)
    assert events == []
    assert lease.handle('up', 36, pid=42)
    assert not lease.handle('down', 36, ('command',), pid=42)
    lease.handle('up', 36, pid=42)
    assert not lease.handle('down', 36, pid=42, eligible=False)
    lease.handle('up', 36, pid=42)
    assert not lease.handle('down', 7, pid=42)
    assert not lease.handle('down', 36, pid=99)
    assert lease.lease is None


def test_interrupted_tap_reconciles_released_and_still_held_keys():
    events = []
    lease = ReviewKeyLease(lambda *x: events.append(x))
    lease.arm('before', 42, ready=True, enabled=True)
    assert lease.handle('down', 36, pid=42)
    lease.disarm()
    lease.reconcile_held({36})
    lease.arm('after', 42, ready=True, enabled=True)
    assert lease.handle('down', 36, repeat=True, pid=42)
    assert events == [('accept', 'before')]
    # Release happened while the tap was unavailable: a fresh physical press
    # must work, without releasing a key that is in fact still held.
    lease.reconcile_held(set())
    assert lease.handle('down', 36, pid=42)
    assert events[-1] == ('accept', 'after')
    assert lease.handle('up', 36, pid=42)


def test_disabled_escape_click_race_and_expiry():
    events = []
    now = [0]
    lease = ReviewKeyLease(lambda *x: events.append(x), clock=lambda: now[0])
    lease.arm('one', 42, ready=True, enabled=False)
    assert lease.handle('down', 36, pid=42)
    assert events == [('unavailable', 'one')]
    assert not lease.claim('one')
    lease.handle('up', 36, pid=42)
    assert lease.handle('down', 53, pid=42)
    lease.disarm()
    assert lease.handle('up', 53, pid=42)
    lease.arm('two', 42, ready=True, enabled=True, ttl=1)
    assert lease.claim('two')  # mouse wins before queued key callback
    assert not lease.claim('two')
    lease.arm('three', 42, ready=True, enabled=True, ttl=1)
    now[0] = 2
    assert not lease.handle('down', 76, ('command',), pid=42)
    lease.handle('up', 76, pid=42)
    assert not lease.handle('down', 76, pid=42, eligible=False)
    lease.handle('up', 76, pid=42)
    assert lease.handle('down', 76, pid=42)
    assert events[-1] == ('expired', 'three')
    assert lease.handle('down', 76, repeat=True, pid=42)
    assert lease.handle('up', 76, pid=42)
    assert lease.lease is None


if __name__ == '__main__':
    tests = [v for k,v in list(globals().items()) if k.startswith('test_')]
    for test in tests:
        test()
        print('ok', test.__name__)
    print(f'{len(tests)}/{len(tests)} passed')
