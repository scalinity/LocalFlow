"""D5 characterization: scope values are compared byte-exact and never
canonicalized at admission (add_entry / update_entry / import accept them
as given), while M06's _url_origin keeps the netloc as delivered. A site
entry typed with a trailing slash, different host case, or padding never
applies; bundle-id case variants are distinct identities (macOS bundle ids
are case-insensitive). Reported as a design question (no contract rule)."""
from _common import *
with TempStore() as t:
    t.vs.add_entry("GitHubTerm", ["git hub term"], scope_kind="site",
                   scope_value="https://github.com/", approved=True)
    t.vs.add_entry("CaseTerm", ["case term"], scope_kind="site",
                   scope_value="https://GitHub.com", approved=True)
    t.vs.add_entry("PadTerm", ["pad term"], scope_kind="app",
                   scope_value=" com.apple.Terminal ", approved=True)
    t.vs.add_entry("BundleTerm", ["bundle term"], scope_kind="app",
                   scope_value="com.apple.terminal", approved=True)
    ctx = V.ScopeContext(app_bundle="com.apple.Terminal", site_origin="https://github.com")
    snap = t.vs.snapshot(ctx)
    for phrase in ("git hub term", "case term", "pad term", "bundle term"):
        out = run(phrase, (), snapshot=snap).text
        expect(f"{phrase!r} applies for the same destination", out != phrase, out)
done()
