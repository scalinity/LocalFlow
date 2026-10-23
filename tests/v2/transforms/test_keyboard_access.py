"""Native permission transitions must not admit partial global key streams."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.permissions import KeyboardAccess
class Listener:
 def __init__(self,available=True):self.starts=0;self.stops=0;self.held=False;self.available=available
 def start(self):self.starts+=1;return self.available
 def stop(self):self.stops+=1
class AccessTests(unittest.TestCase):
 def test_untrusted_identity_never_starts_microphone_trigger_or_transform_tap(self):
  for permissions in ({},{'accessibility':True},{'input_monitoring':True},{'accessibility':False,'input_monitoring':True}):
   hotkey,mouse,tap=Listener(),Listener(),Listener();access=KeyboardAccess([hotkey,mouse],tap)
   access.refresh(permissions)
   self.assertEqual((hotkey.starts,mouse.starts,tap.starts),(0,0,0))
   self.assertFalse(access.dictation_active);self.assertFalse(access.transforms_active)
 def test_grant_activates_existing_listeners_without_restarting_dictation_monitors(self):
  key,tap=Listener(),Listener();access=KeyboardAccess([key],tap)
  self.assertTrue(access.refresh({'accessibility':True,'input_monitoring':True}))
  self.assertFalse(access.refresh({'accessibility':True,'input_monitoring':True}))
  self.assertEqual(key.starts,1);self.assertTrue(access.transforms_active)
 def test_revocation_releases_held_trigger_and_review_then_can_recover(self):
  key,tap=Listener(),Listener();access=KeyboardAccess([key],tap)
  ready={'accessibility':True,'input_monitoring':True};access.refresh(ready);key.held=True
  self.assertTrue(access.refresh({'accessibility':False,'input_monitoring':True}))
  self.assertFalse(key.held);self.assertEqual(key.stops,1);self.assertFalse(access.transforms_active)
  self.assertTrue(access.refresh(ready));self.assertEqual(key.starts,2)
 def test_failed_tap_is_never_advertised_as_an_active_transform_shortcut(self):
  key,tap=Listener(),Listener(False);access=KeyboardAccess([key],tap)
  access.refresh({'accessibility':True,'input_monitoring':True})
  self.assertTrue(access.dictation_active);self.assertFalse(access.transforms_active)
if __name__=='__main__':unittest.main()
