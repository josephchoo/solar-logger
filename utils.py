import config
import time
import solcast
from influxdb import InfluxDBClient

def fill_blanks(flux_client, midnight):
    k = 0
    s = ('SELECT first("P_Exp") as "P_Exp" FROM "%s_daily" where time < %s group by time(1d)') % (config.model, str((midnight - 24 * 3600) * 1000000000))
    zeros=flux_client.query(s, database=config.influxdb_longterm)
    daily = list(zeros.get_points(measurement=config.model + "_daily"))
    print("starting")
    for i in daily:
        if not ((i['P_Exp'] == None) or (i['P_Exp'] == 0)):
            continue

        j = (int(time.mktime(time.strptime(i['time'], "%Y-%m-%dT%H:%M:%SZ"))))
        s = ('SELECT first(M_PTot) as M_PTot_first, last(M_PTot) as M_PTot_last, first(M_PExp) as M_PExp_first, last(M_PExp) as M_PExp_last, first(P_accum) as P_accum_first, last(P_accum) as P_accum_last, max(P_daily) as P_daily, max(P_peak) as P_peak, max(Temp) as Temp  FROM "%s" where time > %s and time < %s and time < %s') % (config.model, str(j * 1000000000), str((j + 24 *3600) * 1000000000), str((midnight - 24 * 3600) * 1000000000))
        try:
            zeros=flux_client.query(s, database=config.influxdb_database)
            m = list(zeros.get_points(measurement=config.model))
            if (len(m) > 0 and len(m[0]) > 0):
                daily1 = {}
                if m[0]['M_PTot_last'] > 0 and m[0]['M_PTot_first'] > 0:
                    daily1['P_Grid'] = float(m[0]['M_PTot_last'] - m[0]['M_PTot_first']) + config.extra_load * 24 / 1000
                    if config.debug:
                        print(s)
                        print(daily1['P_Grid'])
                        print(float(m[0]['M_PTot_last'] - m[0]['M_PTot_first']))
                        print(config.extra_load * 24 / 1000)

                if m[0]['M_PExp_last'] > 0 and m[0]['M_PExp_first'] > 0:
                    daily1['P_Exp'] = float(m[0]['M_PExp_last'] - m[0]['M_PExp_first'])

                if m[0]['P_daily'] > 0:
                    daily1['P_daily'] = float(m[0]['P_daily'])

                if m[0]['Temp'] != None:
                    daily1['Temp'] = float(m[0]['Temp'])

                daily1['P_peak'] = float(m[0]['P_peak'])
                daily1['P_Load'] = float(daily1['P_daily'] - daily1['P_Exp'] + daily1['P_Grid'])
                if len(daily1) < 5:
                    continue

                if daily1['P_Exp'] < daily1['P_daily'] / 3 and daily1['P_Exp'] != 0:
                    continue

                k += 1
                if config.debug:
                    print(i["time"])
                    print((daily1))
                write_influx(flux_client, daily1, config.model+"_daily", config.influxdb_longterm, (j * 1000000000))

        except Exception as e:
            print("fill_blanks error: %s" % str(e))

            print(m)
            continue

        if config.debug:
            print("filled "+str(k)+" daily blanks")

def write_influx(flux_client, measurement, iden, db, t = 0):
    if flux_client is not None:
        metrics = {}
        tags = {}
        if t > 100000000000:
            metrics['time'] = t

        metrics['measurement'] = iden
        tags['location'] = config.location
        if iden == "supla":
          for x in measurement:
             measurement[x]=float(measurement[x])

        metrics['tags'] = tags
        metrics['fields'] = measurement
        metrics =[metrics, ]
        try:
            target=flux_client.write_points(metrics, database=db)
            if not target:
                if config.debug:
                    print(vars(target))
#           print(metrics)
            return target

        except Exception as e:
            print("write_influx error: %s" % str(e))
            ok = False
            if config.debug:
                print("error")
                print(metrics)
                print(db)

            return False
            
def send_measurements(m_start, m_end, flux_client):
    if (not config.soltun) or (config.solfor != 1):
        return

    slices = 5
    s = ('SELECT mean("P_active") as "power" FROM "%s"  WHERE time >= %s and time <= %s GROUP BY time(%sm) fill(none)') % (config.model, str(m_start*1000000000), str(m_end*1000000000), slices)
    if config.debug:
        print(s)
        print("Start: " + time.ctime(m_start))
        print("End:   " + time.ctime(m_end))

    zeros=flux_client.query(s, database=config.influxdb_database)
    m = list(zeros.get_points(measurement=config.model))
    measurements = []
    for i in m:
        if i['power'] == 0:
            continue

        temp = {}
        temp['total_power'] = str(round(i['power'], 3))
        j = int(time.mktime(time.strptime(i["time"], "%Y-%m-%dT%H:%M:%SZ")))
        temp['period_end'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(j + 60 * slices))
        temp['period'] = 'PT'+str(slices)+'M'
        measurements.append(temp)
    #   print(measurements)
    try:
        roof = solcast.post_rooftop_measurements(config.site_UUID, measurements, api_key=config.solcast_key)

    except Exception as e:
        print("send_measurements error: %s" % str(e))
        print("solcast not receiving tuning")
        if config.debug:
            print(vars(roof))
