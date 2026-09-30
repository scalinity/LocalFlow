"""Real AppKit review geometry, result states and retained action routing.
Run through run_isolated.py; never activates or posts desktop events.
"""
import pathlib
import sys
from types import SimpleNamespace as Obj
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
import AppKit
from AppKit import NSApplication, NSAppearance, NSWorkspace, NSWindowStyleMaskTitled
from localflow.v2.ui.transforms_panel import TransformPreviewPanel


def capture(window, name):
    if '--out' not in sys.argv:
        return
    from Foundation import NSDate, NSRunLoop
    import time
    from scripts.v2.companion_screens import window_image
    out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])
    out.mkdir(parents=True, exist_ok=True)
    window.setFrameOrigin_((-4000, 300))
    end = time.monotonic() + .3
    while time.monotonic() < end:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.02))
    assert window_image(window, None, out / (name + '.png')) == 'window'


class Coordinator:
    def __init__(self):
        self.calls = []
    def __getattr__(self, method):
        if method.startswith('tf') or method == 'openHub_':
            return lambda *args: self.calls.append((method, args))
        raise AttributeError(method)


def result(source, output, path='applied', excerpts=(), reason=None):
    return Obj(job=Obj(source=source), output=output, path=path,
               review_excerpts=excerpts, reason=reason)


def test_native_geometry_states_and_focus():
    NSApplication.sharedApplication().setActivationPolicy_(1)
    prior = NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
    panel = TransformPreviewPanel.alloc().init_panel(Coordinator())
    assert panel._buttons['panelAccept:']._text_only, 'Owner chose text-only actions'
    for theme in ('NSAppearanceNameAqua', 'NSAppearanceNameDarkAqua'):
        NSApplication.sharedApplication().setAppearance_(NSAppearance.appearanceNamed_(theme))
        r = result('Send the draft on monday.', 'Send the draft on Monday.')
        panel.show(r, {'source': r.job.source}, Obj(name='Polish'), 'owned-candidate')
        assert panel.name.stringValue() == 'Polish'
        assert '1 change' in panel.count.stringValue()
        assert not panel.panel.styleMask() & NSWindowStyleMaskTitled
        assert not panel.panel.canBecomeKeyWindow()
        assert not panel.panel.canBecomeMainWindow()
        assert panel.panel.contentView().layer().cornerRadius() == 26
        assert panel.panel.frame().size.height < 480
        assert panel.panel.frame().origin.y >= 20
        assert NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier() == prior
        capture(panel.panel, 'transform-bubble-' + ('light' if theme.endswith('NameAqua') else 'dark'))
        panel.panelDismiss_(None)
        assert not panel.panel.isVisible()
    r = result('Keep all conditions.', 'Keep all conditions.', 'needs_review', ('Only after review.',))
    panel.show(r, {'source': r.job.source}, Obj(name='Prompt Engineer'), 'same-candidate')
    assert 'Only after review.' in panel.text.string()
    assert 'needs review' in panel.count.stringValue()
    capture(panel.panel, 'transform-needs-review')
    r = result('Original.', 'Original.', 'fallback_original', reason='generation_failed')
    panel.show(r, {'source': r.job.source}, Obj(name='Concise'), None)
    assert 'generation_failed' in panel.text.string()
    r = result('Long source. ' * 100, 'Long output. ' * 100)
    panel.show(r, {'source': r.job.source}, Obj(name='Polish'), None)
    assert panel.panel.frame().size.height == 480
    assert panel.scroll.hasVerticalScroller()
    panel.reoffer('target changed', r)
    assert not panel._buttons['panelAccept:'].isEnabled()
    assert 'target changed' in panel.count.stringValue()
    panel.panelDismiss_(None)


def test_action_variations():
    for style in ('buttons', 'text'):
        c = Coordinator()
        panel = TransformPreviewPanel.alloc().init_panel(c, action_style=style)
        r = result('Please send the draft on monday, if the review is complete.',
                   'Please send the draft on Monday if the review is complete.')
        panel.show(r, {'source': r.job.source}, Obj(name='Polish'), 'same-candidate')
        assert panel.configure.title() == ''
        assert panel.configure.accessibilityLabel() == 'Configure transform'
        assert panel._buttons['panelAccept:'].frame().origin.x == 24
        assert panel._buttons['panelSaveToScratchpad:'].frame().origin.y == 24
        capture(panel.panel, 'actions-' + style)
        hover = panel._buttons['panelCopy:' if style == 'text' else 'panelAccept:']
        hover.mouseEntered_(None)
        capture(panel.panel, 'actions-' + style + '-hover')
        hover.mouseExited_(None)
        panel.configure.performClick_(None)
        assert c.calls[-1][0] == 'openHub_'
        panel._buttons['panelAccept:'].performClick_(None)
        assert c.calls[-1] == ('tfAcceptTransform', (r, {'source': r.job.source}, 'same-candidate'))
        assert not panel.panel.isVisible()
    from localflow.overlay import Overlay, MODE_TRANSFORMING
    overlay = Overlay.alloc().init()
    overlay._panel.setAlphaValue_(0)
    overlay.showWithMode_(MODE_TRANSFORMING)
    capture(overlay._panel, 'transforming-pill')
    overlay.hide()


def test_seven_action_paths_keep_candidate_identity():
    c = Coordinator()
    panel = TransformPreviewPanel.alloc().init_panel(c)
    r = result('Source.', 'Output.')
    capture, defn, candidate = {'source': 'Source.'}, Obj(name='Polish'), 'owned-candidate'
    for method, expected in [('panelAccept_', 'tfAcceptTransform'), ('panelCopy_', 'tfCopyTransform'), ('panelRetry_', 'tfRetryOriginal'), ('panelSaveToScratchpad_', 'tfSaveToScratchpad'), ('panelConfigure_', 'openHub_')]:
        panel.show(r, capture, defn, candidate)
        getattr(panel, method)(None)
        assert c.calls[-1][0] == expected
        if expected == 'tfAcceptTransform':
            assert c.calls[-1][1] == (r, capture, candidate)
    sender = Obj(representedObject=lambda: 'other-transform')
    for method, expected in [('panelOtherChosen_', 'tfApplyAnother'), ('panelResultChosen_', 'tfTransformOfResult')]:
        panel.show(r, capture, defn, candidate)
        getattr(panel, method)(sender)
        assert c.calls[-1][0] == expected
        assert c.calls[-1][1][0] is r
        assert c.calls[-1][1][1] is capture
    panel.panelDismiss_(None)


if __name__ == '__main__':
    test_native_geometry_states_and_focus()
    print('ok native geometry, themes, bounded scroll, needs review, fallback and no activation')
    test_seven_action_paths_keep_candidate_identity()
    print('ok all seven action paths retain existing coordinator/candidate binding')
    test_action_variations()
    print('ok button/text variants, hover, sliders accessibility and actual native button routing')
    print('3/3 passed')
