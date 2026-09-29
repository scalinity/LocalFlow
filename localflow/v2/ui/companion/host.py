"""The companion's native shell: one NSWindow hosting one WKWebView.

The window keeps every native semantic — traffic lights, move, resize,
minimize, frame autosave, close-hides — and gives the web view the whole
content area (full-size content view, transparent titlebar, an empty
unified toolbar so the traffic lights sit in the same 52 pt band as the
design references). The toolbar carries the two titlebar controls as
native items; the web view draws everything else.

The web view is offline by construction:

- its only document and assets come from ``lfhub://app/`` through a
  ``WKURLSchemeHandler`` that serves files from the bundled build folder
  (no file:// access, no localhost server) with a strict CSP header;
- navigation away from that origin is cancelled, new windows are
  refused, and a content rule list blocks every http(s) load as a second
  wall behind the CSP;
- its website data store is non-persistent, so nothing it shows is
  cached to disk.
"""

from __future__ import annotations

import mimetypes
import pathlib

import objc
import WebKit
from AppKit import (
    NSApp,
    NSAppearance,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSImage,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSApplication,
    NSScreen,
    NSSize,
    NSToolbar,
    NSToolbarItem,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSData, NSHTTPURLResponse, NSObject, NSURL, \
    NSURLRequest, NSUserDefaults

SCHEME = "lfhub"
HOST = "app"
START_URL = f"{SCHEME}://{HOST}/index.html"
WEB_ROOT = pathlib.Path(__file__).resolve().parent / "web"

DEFAULT_SIZE = (1100.0, 760.0)
MIN_SIZE = (900.0, 620.0)
AUTOSAVE_NAME = "LocalFlowHub"  # the frame the Hub window already saved

# The page may load only its own bundled script, style, image and font
# files; it may connect nowhere, embed nothing and submit nothing.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data:; font-src 'self'; connect-src 'none'; "
       "media-src 'none'; object-src 'none'; frame-src 'none'; "
       "worker-src 'none'; base-uri 'none'; form-action 'none'")

# Content-rule regexes have no alternation: one rule per scheme family.
BLOCK_REMOTE_RULES = "[" + ",".join(
    '{"trigger":{"url-filter":"%s"},"action":{"type":"block"}}' % f
    for f in ("^https?://", "^wss?://", "^ftp://")) + "]"


SHELL_LIGHT = (0xF5, 0xF4, 0xF1)
SHELL_DARK = (0x14, 0x13, 0x11)

_TOOLBAR_SIDEBAR = "lf.sidebar"
_TOOLBAR_UTILITY = "lf.utility"

THEMES = ("system", "light", "dark")


def _rgb(c):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(
        c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1.0)


def _shell_color():
    """The shell colour for whichever appearance draws it (no white
    flash before the page paints, in either theme)."""
    def provider(appearance):
        dark = appearance.bestMatchFromAppearancesWithNames_(
            ["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"]) \
            == "NSAppearanceNameDarkAqua"
        return _rgb(SHELL_DARK if dark else SHELL_LIGHT)
    try:
        return NSColor.colorWithName_dynamicProvider_(None, provider)
    except Exception:
        return NSColor.windowBackgroundColor()


def resolve_asset(path: str):
    """URL path → a file inside WEB_ROOT, or None (no traversal, no
    directories, no dotfiles)."""
    rel = (path or "/").lstrip("/") or "index.html"
    parts = rel.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return None
    target = (WEB_ROOT / rel).resolve()
    try:
        target.relative_to(WEB_ROOT)
    except ValueError:
        return None
    return target if target.is_file() else None


_TYPES = {".js": "text/javascript", ".mjs": "text/javascript",
          ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml",
          ".json": "application/json", ".png": "image/png",
          ".woff2": "font/woff2", ".txt": "text/plain"}


def content_type(path: pathlib.Path) -> str:
    return _TYPES.get(path.suffix.lower()) or \
        mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class _SchemeHandler(NSObject, protocols=[
        objc.protocolNamed("WKURLSchemeHandler")]):
    """Serves the bundled build — and nothing else — under lfhub://app/."""

    def webView_startURLSchemeTask_(self, webview, task):
        url = task.request().URL()
        target = resolve_asset(url.path()) if url.host() == HOST else None
        if target is None:
            body, status, ctype = b"", 404, "text/plain"
        else:
            body, status, ctype = target.read_bytes(), 200, \
                content_type(target)
        headers = {"Content-Type": ctype,
                   "Content-Length": str(len(body)),
                   "Content-Security-Policy": CSP,
                   "Cache-Control": "no-store",
                   "X-Content-Type-Options": "nosniff"}
        resp = NSHTTPURLResponse.alloc()\
            .initWithURL_statusCode_HTTPVersion_headerFields_(
                url, status, "HTTP/1.1", headers)
        try:
            task.didReceiveResponse_(resp)
            task.didReceiveData_(NSData.dataWithBytes_length_(body,
                                                              len(body)))
            task.didFinish()
        except Exception:
            pass  # the task was stopped (page reload) — nothing to do

    def webView_stopURLSchemeTask_(self, webview, task):
        pass


class _MessageHandler(NSObject):
    """JS → Python. Only the main frame of our own origin may speak;
    the body must be a string (the JSON envelope). No formal protocol is
    declared: its method type would shadow PyObjC's WebKit metadata
    and leave the reply block without a callable signature."""

    def initWithHost_(self, host):
        self = objc.super(_MessageHandler, self).init()
        self.host = host
        return self

    def userContentController_didReceiveScriptMessage_replyHandler_(
            self, controller, message, reply):
        frame = message.frameInfo()
        origin = frame.securityOrigin() if frame is not None else None
        if frame is None or not frame.isMainFrame() or origin is None \
                or origin.protocol() != SCHEME or origin.host() != HOST:
            reply(None, "refused")
            return
        body = message.body()
        answer = self.host.on_message(str(body) if isinstance(
            body, (str, objc.pyobjc_unicode)) else None)
        reply(answer, None)


class _NavigationDelegate(NSObject):  # no protocol: see _MessageHandler

    def initWithHost_(self, host):
        self = objc.super(_NavigationDelegate, self).init()
        self.host = host
        return self

    def webView_decidePolicyForNavigationAction_decisionHandler_(
            self, webview, action, handler):
        url = action.request().URL()
        frame = action.targetFrame()
        ok = url is not None and url.scheme() == SCHEME \
            and url.host() == HOST and frame is not None \
            and frame.isMainFrame()
        handler(WebKit.WKNavigationActionPolicyAllow if ok
                else WebKit.WKNavigationActionPolicyCancel)

    def webView_didFinishNavigation_(self, webview, navigation):
        self.host.on_page_loaded()

    def webViewWebContentProcessDidTerminate_(self, webview):
        # The web content process died (memory pressure, crash): load the
        # page again; it asks for a fresh snapshot when it boots.
        self.host.on_content_process_terminated()


class _UIDelegate(NSObject, protocols=[
        objc.protocolNamed("WKUIDelegate")]):

    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(  # noqa: E501
            self, webview, configuration, action, features):
        return None  # no pop-up windows, ever


class CompanionWebView(WebKit.WKWebView):
    """Context menus keep text actions only (no Reload, navigation,
    download, open-link or inspector items)."""

    _BLOCKED = ("Reload", "GoBack", "GoForward", "Inspect", "OpenLink",
                "Download", "OpenImage", "OpenFrame", "OpenMedia",
                "CopyLink", "CopyImage", "Share")

    def willOpenMenu_withEvent_(self, menu, event):
        for item in list(menu.itemArray()):
            ident = str(item.identifier() or "")
            if any(b in ident for b in self._BLOCKED):
                menu.removeItem_(item)
        # Drop separators left leading, trailing or doubled.
        items = list(menu.itemArray())
        for i, item in enumerate(items):
            if item.isSeparatorItem() and (
                    i == 0 or i == len(items) - 1
                    or items[i - 1].isSeparatorItem()):
                menu.removeItem_(item)
        objc.super(CompanionWebView, self).willOpenMenu_withEvent_(
            menu, event)


class _ToolbarDelegate(NSObject, protocols=[
        objc.protocolNamed("NSToolbarDelegate")]):

    def initWithHost_(self, host):
        self = objc.super(_ToolbarDelegate, self).init()
        self.host = host
        return self

    def toolbarDefaultItemIdentifiers_(self, toolbar):
        return [_TOOLBAR_SIDEBAR, "NSToolbarFlexibleSpaceItem",
                _TOOLBAR_UTILITY]

    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return self.toolbarDefaultItemIdentifiers_(toolbar)

    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
            self, toolbar, ident, flag):
        if ident == _TOOLBAR_SIDEBAR:
            symbol, label, action = ("sidebar.left", "Toggle Sidebar",
                                     "toggleSidebar:")
        elif ident == _TOOLBAR_UTILITY:
            symbol, label, action = ("ellipsis.circle", "More",
                                     "showUtilityMenu:")
        else:
            return None
        item = NSToolbarItem.alloc().initWithItemIdentifier_(ident)
        item.setLabel_(label)
        item.setToolTip_(label)
        item.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_(  # noqa: E501
            symbol, label))
        item.setTarget_(self)
        item.setAction_(action)
        item.setBordered_(False)
        return item

    def toggleSidebar_(self, sender):
        self.host.on_toolbar("sidebar")

    def showUtilityMenu_(self, sender):
        self.host.on_toolbar("utility")


TITLEBAR_BAND = 52.0


class _DragStrip(NSView):
    """The titlebar band over the web view. The native toolbar items sit
    above it (their container is above the content view); every empty
    point of the band lands here and moves the window, and a double-click
    does what the user set for a titlebar double-click."""

    def mouseDownCanMoveWindow(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        win = self.window()
        if win is None:
            return
        if event.clickCount() == 2:
            action = NSUserDefaults.standardUserDefaults().stringForKey_(
                "AppleActionOnDoubleClick") or "Maximize"
            if action == "Minimize":
                win.performMiniaturize_(None)
            elif action != "None":
                win.performZoom_(None)
            return
        win.performWindowDragWithEvent_(event)


class _WindowDelegate(NSObject, protocols=[
        objc.protocolNamed("NSWindowDelegate")]):

    def initWithHost_(self, host):
        self = objc.super(_WindowDelegate, self).init()
        self.host = host
        return self

    def windowShouldClose_(self, sender):
        # Close ≠ quit (M09-AC04): hide only.
        self.host.on_close()
        return False

    def windowDidBecomeKey_(self, notification):
        self.host.on_key_changed(True)

    def windowDidResignKey_(self, notification):
        self.host.on_key_changed(False)


def _ensure_edit_menu():
    """Text fields take ⌘A/⌘C/⌘V/⌘X/⌘Z from the application's Edit menu;
    a menu-bar-only app has none, so the companion installs a minimal
    one (its key equivalents work without a visible menu bar)."""
    app = NSApplication.sharedApplication()
    if app.mainMenu() is not None:
        return
    main = NSMenu.alloc().init()
    top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Edit", None, "")
    edit = NSMenu.alloc().initWithTitle_("Edit")
    for title, action, key in (("Undo", "undo:", "z"),
                               ("Redo", "redo:", "Z"),
                               ("Cut", "cut:", "x"),
                               ("Copy", "copy:", "c"),
                               ("Paste", "paste:", "v"),
                               ("Select All", "selectAll:", "a")):
        edit.addItem_(NSMenuItem.alloc()
                      .initWithTitle_action_keyEquivalent_(title, action,
                                                           key))
    top.setSubmenu_(edit)
    main.addItem_(top)
    app.setMainMenu_(main)


class CompanionHost:
    """Owns the window and web view. ``client`` receives:
    ``on_message(raw) -> str`` (the bridge), ``on_page_loaded()``,
    ``on_close()``, ``on_toolbar(name)``, ``on_key_changed(bool)`` and
    ``on_appearance_changed()``."""

    def __init__(self, client, theme="system"):
        self.client = client
        self._loaded = False
        self._build(theme)

    # ---- construction ----------------------------------------------------

    def _build(self, theme):
        screen = NSScreen.mainScreen()
        visible = screen.visibleFrame() if screen is not None \
            else NSMakeRect(0, 0, *DEFAULT_SIZE)
        w = min(DEFAULT_SIZE[0], visible.size.width)
        h = min(DEFAULT_SIZE[1], visible.size.height)
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                 | NSWindowStyleMaskMiniaturizable
                 | NSWindowStyleMaskResizable
                 | NSWindowStyleMaskFullSizeContentView)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(visible.origin.x, visible.origin.y, w, h), style,
            NSBackingStoreBuffered, False)
        win.setTitle_("LocalFlow")
        win.setTitleVisibility_(1)  # NSWindowTitleHidden
        win.setTitlebarAppearsTransparent_(True)
        win.setReleasedWhenClosed_(False)
        win.setBackgroundColor_(_shell_color())
        win.setMinSize_(NSSize(min(MIN_SIZE[0], visible.size.width),
                               min(MIN_SIZE[1], visible.size.height)))
        try:
            win.setTitlebarSeparatorStyle_(1)  # NSTitlebarSeparatorStyleNone
        except Exception:
            pass
        self._window_delegate = _WindowDelegate.alloc().initWithHost_(self)
        win.setDelegate_(self._window_delegate)
        self._toolbar_delegate = _ToolbarDelegate.alloc().initWithHost_(self)
        toolbar = NSToolbar.alloc().initWithIdentifier_("LocalFlowCompanion")
        toolbar.setDelegate_(self._toolbar_delegate)
        toolbar.setAllowsUserCustomization_(False)
        toolbar.setDisplayMode_(2)  # NSToolbarDisplayModeIconOnly
        win.setToolbar_(toolbar)
        try:
            win.setToolbarStyle_(3)  # NSWindowToolbarStyleUnified
        except Exception:
            pass
        try:
            win.setFrameAutosaveName_(AUTOSAVE_NAME)
        except Exception:
            pass
        self.window = win
        self.set_theme(theme)

        cfg = WebKit.WKWebViewConfiguration.alloc().init()
        cfg.setWebsiteDataStore_(
            WebKit.WKWebsiteDataStore.nonPersistentDataStore())
        self._scheme_handler = _SchemeHandler.alloc().init()
        cfg.setURLSchemeHandler_forURLScheme_(self._scheme_handler, SCHEME)
        self._message_handler = _MessageHandler.alloc().initWithHost_(self)
        cfg.userContentController()\
            .addScriptMessageHandlerWithReply_contentWorld_name_(
                self._message_handler, WebKit.WKContentWorld.pageWorld(),
                "lf")
        try:
            cfg.preferences().setJavaScriptCanOpenWindowsAutomatically_(
                False)
        except Exception:
            pass
        content = win.contentView()
        wv = CompanionWebView.alloc().initWithFrame_configuration_(
            content.bounds(), cfg)
        wv.setAutoresizingMask_(18)  # width + height
        wv.setAllowsBackForwardNavigationGestures_(False)
        wv.setAllowsMagnification_(False)
        try:
            wv.setValue_forKey_(False, "drawsBackground")
        except Exception:
            pass
        try:
            wv.setUnderPageBackgroundColor_(_shell_color())
        except Exception:
            pass
        self._nav_delegate = _NavigationDelegate.alloc().initWithHost_(self)
        self._ui_delegate = _UIDelegate.alloc().init()
        wv.setNavigationDelegate_(self._nav_delegate)
        wv.setUIDelegate_(self._ui_delegate)
        content.addSubview_(wv)
        self.webview = wv
        b = content.bounds()
        strip = _DragStrip.alloc().initWithFrame_(NSMakeRect(
            0, b.size.height - TITLEBAR_BAND, b.size.width, TITLEBAR_BAND))
        strip.setAutoresizingMask_(2 | 8)  # width; pinned to the top
        content.addSubview_(strip)
        self._drag_strip = strip
        win.setInitialFirstResponder_(wv)
        _ensure_edit_menu()
        self._install_block_list(cfg)
        wv.loadRequest_(NSURLRequest.requestWithURL_(
            NSURL.URLWithString_(START_URL)))

    def _install_block_list(self, cfg):
        store = WebKit.WKContentRuleListStore.defaultStore()
        if store is None:
            return

        def compiled(rule_list, error):
            if rule_list is not None:
                cfg.userContentController().addContentRuleList_(rule_list)
        try:
            store.compileContentRuleListForIdentifier_encodedContentRuleList_completionHandler_(  # noqa: E501
                "LocalFlowCompanionNoRemote", BLOCK_REMOTE_RULES, compiled)
        except Exception:
            pass

    # ---- theme ---------------------------------------------------------------

    def set_theme(self, theme):
        """System follows macOS live; Light/Dark pin the window — and so
        the traffic lights, titlebar and the page's prefers-color-scheme
        — to that appearance."""
        name = {"light": "NSAppearanceNameAqua",
                "dark": "NSAppearanceNameDarkAqua"}.get(theme)
        self.window.setAppearance_(
            NSAppearance.appearanceNamed_(name) if name else None)

    def is_dark(self) -> bool:
        ap = self.window.effectiveAppearance()
        return ap.bestMatchFromAppearancesWithNames_(
            ["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"]) \
            == "NSAppearanceNameDarkAqua"

    # ---- showing ---------------------------------------------------------------

    def show(self):
        self.window.makeKeyAndOrderFront_(NSApp)
        try:
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    def is_visible(self) -> bool:
        return bool(self.window.isVisible())

    def is_key(self) -> bool:
        return bool(self.window.isKeyWindow())

    def webview_has_focus(self) -> bool:
        """The web view (or a view inside it) is the window's first
        responder."""
        fr = self.window.firstResponder()
        view = fr
        while view is not None:
            if view is self.webview:
                return True
            view = view.superview() if hasattr(view, "superview") else None
        return False

    # ---- JS ↔ Python -------------------------------------------------------------

    def on_message(self, raw):
        return self.client.on_message(raw)

    def push(self, json_text):
        """Python → JS: one JSON message to window.__lfBridge.receive.
        Passed as an argument (never spliced into source)."""
        if not self._loaded:
            return False
        self.webview.callAsyncJavaScript_arguments_inFrame_inContentWorld_completionHandler_(  # noqa: E501
            "if (window.__lfBridge) window.__lfBridge.receive(m);",
            {"m": json_text}, None, WebKit.WKContentWorld.pageWorld(), None)
        return True

    def on_page_loaded(self):
        self._loaded = True
        self.client.on_page_loaded()

    def on_content_process_terminated(self):
        self._loaded = False
        self.webview.reload()

    def on_close(self):
        self.window.orderOut_(None)
        self.client.on_close()

    def on_toolbar(self, name):
        self.client.on_toolbar(name)

    def on_key_changed(self, key):
        self.client.on_key_changed(key)

    def on_appearance_changed(self):
        self.client.on_appearance_changed()
