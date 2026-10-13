#!/usr/bin/env python3
"""Switch to an input with its CEC device id, without tvweb.

Used at boot before the server is up: resolves the uniqueId the same way the
stock picker does (launch-point table, then eim's live device list) and
launches the input app with it, so CEC control survives the switch.

Usage: boot-input.py [hdmi4|livetv|...]   (default: last input from eim)
Prints ok:<appid> or fail:<reason>.
"""
import json
import subprocess
import sys


def luna(uri, payload, timeout=8):
    try:
        p = subprocess.run(
            ['luna-send', '-n', '1', '-f', 'luna://' + uri, json.dumps(payload)],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL)
        return json.loads(p.stdout or '{}')
    except Exception:
        return {}


def short_arg():
    if len(sys.argv) > 1 and sys.argv[1]:
        a = sys.argv[1].strip().lower()
        if a == 'livetv':
            return 'livetv', 'com.webos.app.livetv'
        if a.startswith('com.webos.app.'):
            return a.replace('com.webos.app.', ''), a
        return a, 'com.webos.app.' + a
    try:
        d = json.load(open('/var/lib/eim/lastinput'))
        app = (d.get('physicalLastSourceAppId') or d.get('appId') or '')
    except Exception:
        app = ''
    if app == 'com.webos.app.livetv':
        return 'livetv', app
    if app.startswith('com.webos.app.hdmi'):
        return app.replace('com.webos.app.', ''), app
    return '', ''


def unique_id(app_id):
    lp = luna('com.webos.applicationManager/listLaunchPoints', {})
    try:
        for p in (lp.get('launchPoints') or []):
            if p.get('id') == app_id:
                q = p.get('params') or p.get('extraInfo') or {}
                if int(q.get('value', 0)) > 0:
                    return int(q['value'])
                break
    except Exception:
        pass
    st = luna('com.webos.service.eim/getAllInputStatus', {})
    try:
        for d in (st.get('devices') or []):
            want = d.get('appId') or (
                'com.webos.app.' + str(d.get('id', '')).lower().replace('_', ''))
            if want == app_id:
                if (d.get('lastUniqueId') or 0) > 0:
                    return d['lastUniqueId']
                for s in (d.get('subList') or []):
                    if (s.get('uniqueId') or 0) > 0:
                        return s['uniqueId']
                break
    except Exception:
        pass
    return 0


def main():
    _, app_id = short_arg()
    if not app_id:
        print('fail:no-last-input')
        return
    payload = {'id': app_id}
    uid = unique_id(app_id)
    if uid > 0:
        payload['params'] = {'id': 'uniqueId', 'value': str(uid)}
    r = luna('com.webos.applicationManager/launch', payload, timeout=10)
    if isinstance(r, dict) and r.get('returnValue'):
        print('ok:%s uid=%d' % (app_id, uid))
    else:
        print('fail:launch-refused')


if __name__ == '__main__':
    main()
