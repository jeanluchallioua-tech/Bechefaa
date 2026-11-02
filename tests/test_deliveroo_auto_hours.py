import copy
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock
from clean_caisse.deliveroo_production_auto_phase6 import decision_for_order

class AutoHoursPolicyTests(unittest.TestCase):
 def order(self,asap=True):
  return {'asap':asap,'start_preparing_at':'2099-03-03T12:00:00+01:00'}
 def test_asap_uses_the_current_shared_deliveroo_state(self):
  engine=Mock(return_value={'open':True});now=datetime(2099,3,2,12,tzinfo=timezone.utc)
  self.assertEqual(decision_for_order(self.order(),engine,now),{'status':'accepted'})
  self.assertEqual(engine.call_args.kwargs,{'now':now,'channel':'deliveroo','strict':True})
 def test_closed_uses_required_rejection_reason(self):
  result=decision_for_order(self.order(),lambda **kwargs:{'open':False})
  self.assertEqual(result['status'],'rejected');self.assertEqual(result['reject_reason'],'closing_early')
 def test_future_order_is_checked_at_its_preparation_slot_not_now(self):
  now=datetime(2099,3,2,12,tzinfo=timezone.utc);engine=Mock(return_value={'open':True})
  self.assertEqual(decision_for_order(self.order(False),engine,now)['status'],'accepted')
  self.assertEqual(engine.call_args.kwargs['now'],datetime.fromisoformat('2099-03-03T12:00:00+01:00'))
 def test_past_scheduled_is_checked_now(self):
  now=datetime(2099,3,4,12,tzinfo=timezone.utc);engine=Mock(return_value={'open':True})
  decision_for_order(self.order(False),engine,now)
  self.assertEqual(engine.call_args.kwargs['now'],now)
 def test_missing_or_failing_hours_never_becomes_acceptance(self):
  for engine in (None,lambda **kwargs:{},lambda **kwargs:{'open':None},Mock(side_effect=RuntimeError('unavailable'))):
   with self.assertRaises((ValueError,RuntimeError)):decision_for_order(self.order(),engine)
 def test_naive_scheduled_time_is_rejected(self):
  order=self.order(False);order['start_preparing_at']='2099-03-03T12:00:00'
  with self.assertRaises(ValueError):decision_for_order(order,lambda **kwargs:{'open':True})

if __name__=='__main__':unittest.main()
