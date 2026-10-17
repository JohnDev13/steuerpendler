#!/usr/bin/env python3
"""Bounded real-r5py diagnostic, NOT a metric conformance pass or Swiss data.

Run in pinned venv with JAVA_HOME set and --r5-classpath PATH. All geography,
services and agency below are invented TEST fixtures around Helsinki coordinates;
no result is written to site/data. r5py parses --max-memory/--r5-classpath itself.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import resource
import sys
import tempfile
import time
import zipfile


def fixture(directory):
    """Deterministic synthetic GTFS for actual R5 loading; no custom routing."""
    tables = {
        'agency.txt': [('agency_id', 'agency_name', 'agency_url', 'agency_timezone'),
                       ('SYN', 'SYNTHETIC ONLY', 'https://example.invalid', 'Europe/Helsinki')],
        'stops.txt': [('stop_id','stop_name','stop_lat','stop_lon','location_type','parent_station'),
            ('A','Synthetic parent A',60,24,1,''),
            ('A1','Synthetic platform A1',60,24,0,'A'),
            ('A2','Synthetic platform A2',60,24.0002,0,'A'),
            ('X','Synthetic transfer X',60,24.05,0,''),
            ('Y','Synthetic transfer Y',60,24.052,0,''),
            ('B','Synthetic parent B',60,24.1,1,''),
            ('B1','Synthetic platform B1',60,24.1,0,'B'),
            ('N','Synthetic no-service stop',60,24.0998,0,'')],
        'routes.txt': [('route_id','agency_id','route_short_name','route_long_name','route_type'),
            ('DIRECT','SYN','S','Synthetic direct',3),
            ('TRANSFER1','SYN','T1','Synthetic transfer first',3),
            ('TRANSFER2','SYN','T2','Synthetic transfer second',3)],
        'calendar_dates.txt': [('service_id','date','exception_type'),('SYN','20270112',1)],
        'feed_info.txt': [('feed_publisher_name','feed_publisher_url','feed_lang','feed_start_date','feed_end_date','feed_version'),
            ('SYNTHETIC ONLY','https://example.invalid','en','20270112','20270112','synthetic-v1')],
        'trips.txt': [('route_id','service_id','trip_id')],
        'stop_times.txt': [('trip_id','arrival_time','departure_time','stop_id','stop_sequence')],
    }
    def trip(name, route, origin, dest, departure, duration):
        seconds = sum(int(v) * f for v, f in zip(departure.split(':'), (3600,60,1)))
        arrival = str(dt.timedelta(seconds=seconds + duration)).zfill(8)
        tables['trips.txt'].append((route,'SYN',name))
        tables['stop_times.txt'].extend([(name,departure,departure,origin,1), (name,arrival,arrival,dest,2)])
    trip('outside-before','DIRECT','A1','B1','06:29:59',30)
    trip('lower-inclusive','DIRECT','A1','B1','06:30:00',600)
    trip('rare-second','DIRECT','A2','B1','07:13:17',121)
    trip('upper-inclusive','DIRECT','A1','B1','08:30:00',60)
    trip('outside-after','DIRECT','A1','B1','08:30:01',30)
    for hour, minute in [(h,m) for h in (6,7,8) for m in range(0,60,10)
                         if (h,m) >= (6,40) and (h,m) <= (8,20)]:
        trip(f'slow-{hour}-{minute}','DIRECT','A1','B1',f'{hour:02}:{minute:02}:00',1200)
    trip('transfer-first','TRANSFER1','A1','X','07:00:00',300)
    trip('transfer-second','TRANSFER2','Y','B1','07:09:00',300)
    path = directory / 'synthetic-only.gtfs.zip'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, rows in sorted(tables.items()):
            out = io.StringIO(newline='')
            csv.writer(out, lineterminator='\n').writerows(rows)
            info = zipfile.ZipInfo(name, date_time=(2000,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, out.getvalue())
    return path, tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=pathlib.Path, required=True)
    args, _ = parser.parse_known_args()
    # Force before import (never allow r5py's 80% default on this host).
    if '--max-memory' in sys.argv:
        raise SystemExit('Probe owns heap setting: do not supply --max-memory')
    sys.argv.extend(['--max-memory','512M'])
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    start = time.monotonic()
    report = {'status':'running', 'syntheticOnly':True, 'conformancePassed':False,
              'scope':'actual r5py diagnostic, not full §8 fixture suite',
              'startedUtc':dt.datetime.now(dt.timezone.utc).isoformat()}
    exit_code = 0
    try:
        import geopandas as gpd
        from shapely.geometry import Point
        import r5py
        import jpype
        import java.lang
        from r5py.util import Config
        # A single routing thread. No full-network or multiprocessing execution.
        r5py.DetailedItineraries.NUM_THREADS = 1
        r5py.TravelTimeMatrix.NUM_THREADS = 1
        report.update(r5py=r5py.__version__, java=str(java.lang.System.getProperty('java.runtime.version')),
                      javaVendor=str(java.lang.System.getProperty('java.vendor')),
                      maxHeapBytes=int(java.lang.Runtime.getRuntime().maxMemory()))
        if report['maxHeapBytes'] != 512 * 1024**2:
            raise RuntimeError('JVM heap differs from hard safety limit')
        with tempfile.TemporaryDirectory(prefix='travel-synthetic-') as tmp:
            directory = pathlib.Path(tmp)
            gtfs, tables = fixture(directory)
            pbf = directory / 'synthetic-only.osm.pbf'
            # Use R5's own OSM PBF writer, not real OSM or an extra dependency.
            sink = jpype.JClass('com.conveyal.osmlib.OSMEntitySink').forFile(str(pbf))
            sink.writeBegin()
            # R5 removes tiny disconnected islands: a connected >40-edge grid
            # avoids testing that cleanup rather than transit routing.
            coords = [(60 + row * 0.001, 24 + col * 0.002)
                      for row in range(5) for col in range(51)]
            for i, (lat,lon) in enumerate(coords, 1):
                sink.writeNode(i, jpype.JClass('com.conveyal.osmlib.Node')(lat,lon))
            lines = [[row * 51 + col + 1 for col in range(51)] for row in range(5)]
            lines += [[row * 51 + col + 1 for row in range(5)] for col in range(51)]
            for way_id, nodes in enumerate(lines, 1):
                way = jpype.JClass('com.conveyal.osmlib.Way')()
                way.nodes = jpype.JArray(jpype.JLong)(nodes)
                way.addTag('highway','residential')
                way.addTag('foot','yes')
                sink.writeWay(way_id,way)
            sink.writeEnd()
            report['fixtures'] = {p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                                  for p in (gtfs,pbf)}
            report['gtfsTables'] = tables
            network = r5py.TransportNetwork(pbf,gtfs)  # strict GTFS errors, no allow_errors
            origin = gpd.GeoDataFrame({'id':['SYN-A']},geometry=[Point(24,60)],crs=4326)
            destinations = gpd.GeoDataFrame({'id':['SYN-B','SYN-N']},
                                          geometry=[Point(24.1,60),Point(24.0998,60)],crs=4326)
            departure = dt.datetime(2027,1,12,6,30)
            options = dict(departure=departure,departure_time_window=dt.timedelta(hours=2),
                           transport_modes=[r5py.TransportMode.TRANSIT],
                           access_modes=[r5py.TransportMode.WALK],egress_modes=[r5py.TransportMode.WALK],
                           max_time=dt.timedelta(hours=2))
            report['options'] = {k:str(v) for k,v in options.items()}
            matrix = r5py.TravelTimeMatrix(network,origin,destinations,percentiles=[1],**options)
            import pandas as pd
            report['matrixPercentile1'] = json.loads(pd.DataFrame(matrix).to_json(orient='records'))
            detailed = r5py.DetailedItineraries(network,origin,destinations,**options)
            cols = [c for c in detailed.columns if c != 'geometry']
            report['detailedItineraries'] = [{str(k):str(v) for k,v in row.items()}
                                            for row in detailed[cols].to_dict(orient='records')]
            # Authentic wrapper truncates seconds; record actual Java request value.
            request = r5py.RegionalTask(network,departure=departure.replace(hour=7,minute=13,second=17),
                                       departure_time_window=dt.timedelta(minutes=5))
            report['secondPrecisionRequest'] = {'requested':'07:13:17',
                'actualJavaFromTime':int(request._regional_task.fromTime),
                'actualJavaFromTimeClock':str(dt.timedelta(seconds=int(request._regional_task.fromTime)))}
            report['expectedFromFixtureOnly'] = {
                'exactFirstBoardingSeconds_A_to_B':60,
                'reason':'08:30:00 inclusive; 06:29:59/08:30:01 are excluded',
                'notOfficialReference':True}
            report['status'] = 'diagnostic_completed_metric_blocked'
            report['blockers'] = ['Sampled percentiles include preboarding/access/egress and cannot prove exact minimum.',
                'DetailedItineraries uses random sampled departure states and unconstrained nearby-stop access/egress.',
                'RegionalTask discards departure seconds. No validated exact nominated-platform adapter exists.']
    except Exception as exc:
        import traceback
        report.update(status='diagnostic_failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        exit_code = 2
    report['elapsedSeconds'] = time.monotonic()-start
    report['peakProcessRssBytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('gtfsTables','detailedItineraries')},indent=2))
    return exit_code


if __name__ == '__main__': sys.exit(main())
