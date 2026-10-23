"""Native representation round trips on private pasteboards; no user clipboard."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from AppKit import NSPasteboard, NSRTFPboardType
from Foundation import NSData
from localflow.v2.insertion.hosts import SystemPasteboard
from localflow.v2.insertion.clipboard import ClipboardTransaction


class NativeClipboardTests(unittest.TestCase):
    def board(self, pairs):
        board = SystemPasteboard()
        board._pb = NSPasteboard.pasteboardWithUniqueName()
        board._pb.declareTypes_owner_([t for t, _ in pairs], None)
        for kind, value in pairs:
            self.assertTrue(board._pb.setData_forType_(NSData.dataWithBytes_length_(value, len(value)), kind))
        return board

    def snapshot(self, board):
        return {str(kind): bytes(board.data_for_type(kind)) for kind in board.types()}

    def test_chromium_copy_and_legacy_aliases_restore_byte_for_byte(self):
        pairs = [('public.utf8-plain-text', b'synthetic text'), ('NSStringPboardType', b'synthetic text'),
                 ('org.chromium.internal.source-rfh-token', b'{"synthetic":true}'),
                 ('org.chromium.source-url', b'https://synthetic.invalid')]
        board = self.board(pairs); before = self.snapshot(board)
        transaction = ClipboardTransaction(board)
        self.assertFalse(transaction.capture().unsupported_types)
        transaction.publish('temporary synthetic replacement')
        self.assertTrue(transaction.restore_if_owned())
        self.assertEqual(before, self.snapshot(board))

    def test_html_and_rtf_legacy_flavors_restore(self):
        for pairs in ([('public.html', b'<p>synthetic</p>'), ('Apple HTML pasteboard type', b'<p>synthetic</p>')],
                      [('public.rtf', b'{\\rtf1 synthetic}'), (str(NSRTFPboardType), b'{\\rtf1 synthetic}')]):
            with self.subTest(types=[t for t, _ in pairs]):
                board = self.board(pairs); before = self.snapshot(board)
                transaction = ClipboardTransaction(board)
                self.assertFalse(transaction.capture().unsupported_types)
                transaction.publish('temporary synthetic replacement')
                self.assertTrue(transaction.restore_if_owned())
                self.assertEqual(before, self.snapshot(board))

    def test_remote_text_metadata_round_trips_without_decoding(self):
        import plistlib
        board = self.board([
            ('public.utf8-plain-text', 'synthetic é'.encode()),
            ('public.text', 'synthetic é'.encode()),
            ('com.apple.is-remote-clipboard', plistlib.dumps(True, fmt=plistlib.FMT_BINARY))])
        before = self.snapshot(board)
        transaction = ClipboardTransaction(board)
        self.assertFalse(transaction.capture().unsupported_types)
        transaction.publish('temporary synthetic replacement')
        self.assertTrue(transaction.restore_if_owned())
        self.assertEqual(before, self.snapshot(board))

    def test_new_copy_wins_on_the_native_generation(self):
        board = self.board([('public.utf8-plain-text', b'original synthetic')])
        transaction = ClipboardTransaction(board); transaction.capture(); transaction.publish('temporary synthetic')
        board.clear_and_write_text('newer synthetic copy')
        self.assertFalse(transaction.restore_if_owned())
        self.assertEqual('user_copy_won', transaction.restore_skipped_reason)
        self.assertEqual('newer synthetic copy', board.string_for_type('public.utf8-plain-text'))

    def test_file_promises_remain_explicitly_unsupported(self):
        board = self.board([('com.apple.pasteboard.promised-file-url', b'synthetic promise')])
        capture = ClipboardTransaction(board).capture()
        self.assertIn('com.apple.pasteboard.promised-file-url', capture.unsupported_types)
        self.assertEqual(set(board.types()), set(capture.unsupported_types))
        self.assertEqual([], capture.items)


if __name__ == '__main__':
    unittest.main()
