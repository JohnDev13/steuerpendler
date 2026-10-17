"""Synthetic unit cases only: no Swiss timetable/reference values."""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'travel'))
import primitives as p


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.meta = {'schemaVersion': 1, 'releaseId': 'a' * 64}
        self.access = {'meta': self.meta, 'gemeinden': {
            '1': ['SYN-A', 'Synthetic A', 10],
            '2': ['SYN-A', 'Synthetic A', 0], '3': None}}
        self.files = {k: {'meta': self.meta, 'to': int(k), 'rows': [[1, 0], [2, 0]]}
                      for k in ('1', '2')}

    def check(self):
        return p.validate_dataset(self.access, self.files, {'1', '2', '3'}, 'a' * 64)

    def test_complete_and_null_access_dataset(self):
        self.assertIsNone(self.check())

    def test_bad_rows_and_id_sets_fail_closed(self):
        bad = [ [[1, 0], [1, 2]], [[2, 0], [1, 0]], [[1, 0], [99, 2]],
                [[1, 0], [2, 61]], [[1, 0], [2, float('nan')]],
                [[1, 0], [True, 0]], [[1, 0]], [[1, 0], [2, 1]],
                [[1, 0], [2, 0], [3, 2]] ]
        for rows in bad:
            with self.subTest(rows=rows):
                self.setUp()
                self.files['1']['rows'] = rows
                with self.assertRaises(p.ValidationError): self.check()
        for key in ('1', '3', '01'):
            self.setUp()
            self.access['gemeinden'].pop(key, None)
            if key == '01': self.access['gemeinden'][key] = None
            with self.assertRaises(p.ValidationError): self.check()

    def test_missing_extra_files_and_release_mismatch(self):
        for change in ('missing', 'extra', 'release', 'self', 'walk'):
            self.setUp()
            if change == 'missing': del self.files['1']
            if change == 'extra': self.files['3'] = copy.deepcopy(self.files['1'])
            if change == 'release': self.files['1']['meta'] = {'schemaVersion': 1, 'releaseId': 'b' * 64}
            if change == 'self': self.files['1']['to'] = 2
            if change == 'walk': self.access['gemeinden']['1'][2] = 61
            with self.subTest(change=change), self.assertRaises(p.ValidationError): self.check()


class CalendarGroupingTests(unittest.TestCase):
    def test_calendar_exceptions_parent_aggregation_seconds_and_dedup(self):
        import datetime as dt
        day = dt.date(2027, 1, 12)  # synthetic test date, not approved Swiss day
        cal = [dict(service_id='weekday', start_date='20270101', end_date='20270131',
                    monday='1',tuesday='1',wednesday='1',thursday='1',friday='1',saturday='0',sunday='0')]
        exceptions = [dict(service_id='weekday',date='20270112',exception_type='2'),
                      dict(service_id='special',date='20270112',exception_type='1')]
        active = p.active_services(day,cal,exceptions)
        self.assertEqual(active, {'special'})
        self.assertEqual(p.active_services(day,cal,[]), {'weekday'})
        self.assertEqual(p.active_services(dt.date(2027,2,2),cal,[]), set())
        stops = {'a1':{'parent_station':'A'},'a2':{'parent_station':'A'},
                 'b':{'parent_station':''},'A':{'location_type':'1'}}
        trips = {'t1':'special','t2':'weekday','t3':'special'}
        rows = [dict(trip_id=t,stop_id=s,stop_sequence=n,departure_time=d)
                for t,s,n,d in [('t1','a1',1,'06:00:00'),('t1','a2',2,'09:00:00'),
                                ('t2','b',1,'07:00:00'),('t3','b',1,'08:00:17'),
                                ('t3','b',2,'05:59:59'),('t3','b',3,'09:00:01'),
                                ('t3','b',4,'25:00:00')]]
        self.assertEqual(p.rank_stations(stops,trips,rows+[rows[0]],active,{'a1','a2','b'}),
                         [('A',2),('b',1)])
        self.assertEqual(p.rank_stations(stops,trips,[rows[0],rows[3]],active,{'a1','b'}),
                         [('A',1),('b',1)])
        self.assertEqual(p.rank_stations(stops,trips,rows,set(),set(stops)), [])
        with self.assertRaises(p.ValidationError):
            p.active_services(day,cal,exceptions+[exceptions[0]])
        conflict = dict(rows[0],departure_time='06:01:00')
        with self.assertRaises(p.ValidationError):
            p.rank_stations(stops,trips,rows+[conflict],active,set(stops))


class EndpointFilterTests(unittest.TestCase):
    def test_speed_thresholds_shared_station_zero_and_rounding(self):
        self.assertEqual(p.pair_qa('A','A',0,0), 'passed')
        self.assertEqual(p.pair_qa('A','B',10.1,5), 'passed')  # v exactly 100
        self.assertEqual(p.pair_qa('A','B',15.1,5), 'review')  # v exactly 150
        self.assertEqual(p.pair_qa('A','B',15.1001,5), 'blocked')
        self.assertEqual(p.pair_qa('A','B',0.05,1), 'passed')
        for a,b,d,m in [('A','B',0,0),('A','A',1,0),('A','A',0,1),
                          ('A','B',float('nan'),2),('A','B',1,-1)]:
            with self.subTest(a=a,b=b,d=d,m=m), self.assertRaises(p.ValidationError):
                p.pair_qa(a,b,d,m)
        self.assertEqual(p.reachable(None,0,15,60,False), False)
        self.assertEqual(p.reachable(10,None,15,60,False), False)
        self.assertFalse(p.reachable(10,0,10,5,True))
        self.assertTrue(p.reachable(10,0,10,5,False))
        self.assertFalse(p.reachable(10,0,9,60,False))
        for limit in range(61):
            if p.reachable(5,12,10,limit,True):
                self.assertTrue(p.reachable(5,12,10,min(60,limit+1),True))


if __name__ == '__main__': unittest.main()
