"""Review and permission notices stay on a usable native display."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]))
from AppKit import NSMakeRect
from localflow.v2.ui.transforms_panel import clamped_panel_origin
class BoundsTests(unittest.TestCase):
 def test_unpositioned_overlay_cannot_place_half_the_notice_offscreen(self):
  card=NSMakeRect(0,0,580,300);screen=NSMakeRect(0,40,1440,860)
  self.assertEqual(clamped_panel_origin(-250,0,card,screen),(12,52))
 def test_every_corner_and_negative_display_origin_keeps_the_full_card_visible(self):
  for screen in [NSMakeRect(0,30,1440,870),NSMakeRect(-1600,60,1600,940),NSMakeRect(0,1000,1280,780)]:
   for x,y in [(-5000,-5000),(5000,5000),(-200,1800),(1200,20)]:
    card=NSMakeRect(0,0,580,480);a,b=clamped_panel_origin(x,y,card,screen)
    self.assertGreaterEqual(a,screen.origin.x+12);self.assertGreaterEqual(b,screen.origin.y+12)
    self.assertLessEqual(a+580,screen.origin.x+screen.size.width-12)
    self.assertLessEqual(b+480,screen.origin.y+screen.size.height-12)
if __name__=='__main__':unittest.main()

class StatusPresentationTests(unittest.TestCase):
 def test_unavailable_notice_clears_previous_diff_attributes_and_ready_title(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  from AppKit import NSMutableAttributedString, NSStrikethroughStyleAttributeName, NSApplication
  from localflow.v2.ui.transforms_panel import TransformPreviewPanel
  NSApplication.sharedApplication()
  storage=NSMutableAttributedString.alloc().initWithString_attributes_('old removed source',{NSStrikethroughStyleAttributeName:1})
  text=SimpleNamespace(textStorage=lambda:storage,setAccessibilityHelp_=Mock())
  state=SimpleNamespace(panel=Mock(),name=Mock(),count=Mock(),text=text,
    _buttons={'accept':Mock()},_fit_height=Mock(),_anchor=Mock())
  state._append=lambda value,message,kind:TransformPreviewPanel._append(state,value,message,kind)
  TransformPreviewPanel.show_status(state,'Return to the original terminal pane.')
  self.assertEqual(storage.string(),'Return to the original terminal pane.')
  self.assertIsNone(storage.attribute_atIndex_effectiveRange_(NSStrikethroughStyleAttributeName,0,None)[0])
  state.panel.setTitle_.assert_called_once_with('Transform unavailable — original unchanged')
  self.assertIsNone(state._state['result'])
  state._buttons['accept'].setEnabled_.assert_called_once_with(False)
