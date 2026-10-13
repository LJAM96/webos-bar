#!/usr/bin/env python3
"""HOME-key watcher: GREEN raises the bottom-bar overlay, HOME is stock unless
no-Home mode is on.

Passive listener (never grabs the remote): evdev delivers every event to each
open fd, so all keys keep working normally even if this dies.

GREEN (399, standard Linux color code) has no system action on HDMI inputs,
so it raises the bar instantly with no flash and no input switch at all.

With the no-home marker present (/var/lib/barwatcher/no-home, maintained by
the 48-nohome boot hook that disables the Home app), HOME raises the bar
directly instead of opening full Home.

Strand recovery: backing out of an app with no Home to land on leaves an
empty foreground. When that happens and the remote then sits idle a couple
of seconds, the TV returns to the last-used input by itself; any keypress in
between cancels it.

Toggle: GREEN while the bar is open closes it.
"""
import glob
import json
import os
import select
import struct
import subprocess
import time
import urllib.request

BAR_ID = 'com.lukemulvaney.bar'
HOME_CODE = 773
GREEN_CODE = 399
DEBOUNCE_S = 0.5
TVWEB = 'http://127.0.0.1:8080'
LOG = '/var/lib/barwatcher/watch.log'
EIM_LASTINPUT = '/var/lib/eim/lastinput'
HOME_APP = 'com.webos.app.home'
NO_HOME_MARK = '/var/lib/barwatcher/no-home'
FG_POLL_S = 1.0
BOUNCE_DELAY_S = 2.0
BOUNCE_COOLDOWN_S = 10.0
CECFIX_MARK = 'launchInputWithCec'
LP_MARK = 'launchPointsApi'
CECFIX_CHECK_S = 600

LP = struct.calcsize('l')
EVT_FMT = 'qqHHI' if LP == 8 else 'llHHI'
EVT_SZ = struct.calcsize(EVT_FMT)
EV_KEY = 1

_last_cecfix = 0.0
_last_home_key = 0.0
_last_bounce = 0.0
_last_any_key = 0.0
_last_backstop = 0.0
BACKSTOP_S = 10.0
_prev_fg = None
_last_fg_poll = 0.0
_bounce_at = 0.0


def tv_control(action, value, timeout=10):
    try:
        req = urllib.request.Request(
            TVWEB + '/api/control',
            data=json.dumps({'action': action, 'value': value}).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or '{}')
    except Exception as e:
        log('tvweb control %s=%s failed: %s' % (action, value, e))
        return {}


def last_input_control():
    # Where the TV itself records the last physical input, e.g.
    # {"physicalLastSourceAppId": "com.webos.app.hdmi4", ...}.
    try:
        with open(EIM_LASTINPUT) as f:
            d = json.load(f)
        app = (d.get('physicalLastSourceAppId') or d.get('appId') or '')
        if app == 'com.webos.app.livetv':
            return 'livetv'
        if app.startswith('com.webos.app.hdmi'):
            return app.replace('com.webos.app.', '')
    except Exception as e:
        log('lastinput read failed: %s' % e)
    return ''


def stranded(fg):
    # Home with no HOME key behind it (backed out of an app), or no
    # foreground app at all (as when the Home app is gone).
    return fg == HOME_APP or fg == ''


def is_live_input(app_id):
    return app_id == 'com.webos.app.livetv' or \
        app_id.startswith('com.webos.app.hdmi')


def backstop_home():
    # No-Home standard: a Home renderer should never be foreground. If one
    # is (early boot, stray launch), kill it so video shows through again.
    # Throttled; surface-manager falls back to the previous window.
    global _last_backstop
    now = time.time()
    if now - _last_backstop < BACKSTOP_S:
        return
    _last_backstop = now
    me = os.getpid()
    killed = False
    try:
        for pid in filter(str.isdigit, os.listdir('/proc')):
            try:
                if int(pid) == me:
                    continue
                with open('/proc/%s/cmdline' % pid, 'rb') as f:
                    cmd = f.read().decode('utf8', 'ignore')
                if 'flutter' in cmd and HOME_APP in cmd:
                    os.kill(int(pid), 9)
                    killed = True
            except Exception:
                continue
    except Exception:
        return
    if killed:
        log('backstop killed home renderer')


def track_fg():
    # Called every couple of seconds. Arms a return-to-input when the screen
    # strands after leaving a real app. A deliberate HOME press or any later
    # keypress disarms it. Transitions out of live inputs are ignored: those
    # are input switches in flight, not strandings.
    global _prev_fg, _last_fg_poll, _bounce_at
    now = time.time()
    if now - _last_fg_poll < FG_POLL_S:
        return
    _last_fg_poll = now
    fg = foreground()
    if fg == HOME_APP and os.path.exists(NO_HOME_MARK):
        backstop_home()
    prev, _prev_fg = _prev_fg, fg
    if not stranded(fg):
        return
    if not prev or prev == HOME_APP or prev == '' or is_live_input(prev):
        return
    if now - _last_home_key < 3.0:
        return
    _bounce_at = now + BOUNCE_DELAY_S
    log('stranded on %s (from %s), bounce armed' % (fg or 'nothing', prev))


def maybe_bounce():
    global _bounce_at, _last_bounce
    if not _bounce_at or time.time() < _bounce_at:
        return
    _bounce_at = 0.0
    fg = foreground()
    if not stranded(fg):
        return
    if time.time() - _last_any_key < BOUNCE_DELAY_S:
        log('bounce cancelled, remote in use')
        return
    if time.time() - _last_home_key < 3.0:
        return
    if time.time() - _last_bounce < BOUNCE_COOLDOWN_S:
        return
    target = last_input_control()
    if not target:
        return
    _last_bounce = time.time()
    log('bouncing %s -> %s' % (fg or 'nothing', target))
    tv_control('input', target)


def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 65536:
            os.rename(LOG, LOG + '.old')
        with open(LOG, 'a') as f:
            f.write('%s %s\n' % (time.strftime('%H:%M:%S'), msg))
    except OSError:
        pass


def luna(uri, payload, timeout=8):
    try:
        p = subprocess.run(
            ['luna-send', '-n', '1', '-f', 'luna://' + uri, json.dumps(payload)],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL)
        return json.loads(p.stdout or '{}')
    except Exception as e:
        log('luna %s failed: %s' % (uri, e))
        return {}


def foreground():
    r = luna('com.webos.applicationManager/getForegroundAppInfo', {})
    return (r.get('appId') or '') if isinstance(r, dict) else ''


def bar_open():
    # Overlay windows never become the foreground app, so FG can't tell us
    # the bar is up. The running-app list can.
    r = luna('com.webos.applicationManager/running', {})
    try:
        for a in (r.get('running') or []):
            aid = a.get('id') if isinstance(a, dict) else a
            if aid == BAR_ID:
                return True
    except Exception:
        pass
    return False


def show_bar():
    luna('com.webos.applicationManager/launch', {'id': BAR_ID})


def close_bar():
    luna('com.webos.applicationManager/closeByAppId', {'id': BAR_ID})


def wait_bar(want_open, timeout_s=4.0):
    # The running list lags both registration and teardown by seconds, so a
    # bare read right after acting lies. Poll until the state settles, making
    # every press do the right thing instead of guessing from timestamps.
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if bar_open() == want_open:
            return True
        time.sleep(0.2)
    return bar_open() == want_open


def close_home():
    # No-Home standard: the HOME key still reaches surface-manager, which
    # launches stock Home behind our backs at the same time as we raise the
    # bar. Close it gracefully (not SIGKILL, so SAM treats it as a normal
    # close) so video is what sits behind the overlay. Fire-and-forget and
    # harmless when Home isn't running.
    luna('com.webos.applicationManager/closeByAppId', {'id': HOME_APP})


def on_green(fg):
    # No restore dance and no input gate: the overlay composites over any
    # foreground app, and switching inputs from a tile goes through tvweb
    # with the CEC device id. Dismissing returns to whatever was showing.
    log('GREEN pressed, fg=%s' % fg)
    if fg == HOME_APP and os.path.exists(NO_HOME_MARK):
        close_home()
    show_bar()


def on_key(code):
    if code == GREEN_CODE:
        if bar_open():
            log('GREEN pressed with bar open, closing bar')
            close_bar()
            wait_bar(False)
            return
        on_green(foreground())
        wait_bar(True)
        return
    # HOME_CODE: stock behavior opens full Home; only toggle-close the bar.
    # No-Home standard: with the no-home marker present, HOME raises the bar
    # directly and stock Home (launched by the system on the same keypress)
    # is closed at once, so it never sits behind the overlay.
    if os.path.exists(NO_HOME_MARK):
        if bar_open():
            log('HOME(test) closing bar')
            close_bar()
            wait_bar(False)
        else:
            log('HOME(test) raising bar')
            close_home()
            show_bar()
            wait_bar(True)
        return
    if bar_open():
        log('HOME pressed with bar open, closing bar')
        close_bar()


def cecfix_guard(force=False):
    global _last_cecfix
    now = time.time()
    if not force and now - _last_cecfix < CECFIX_CHECK_S:
        return
    _last_cecfix = now
    try:
        with open('/var/lib/tvweb/lib/controls.js') as f:
            controls_ok = CECFIX_MARK in f.read()
    except Exception:
        controls_ok = True
    try:
        with open('/var/lib/tvweb/lib/routes.js') as f:
            routes_ok = LP_MARK in f.read()
    except Exception:
        routes_ok = True
    if controls_ok and routes_ok:
        return
    log('server patch missing (tvweb update?), reapplying')
    ok = True
    if not controls_ok:
        ok = cecfix_apply() and ok
    if not routes_ok:
        ok = lp_apply() and ok
    if ok:
        log('server patch reapplied, restarting tvweb')
        subprocess.run(['/var/lib/tvweb/tvwebctl', 'restart'],
                       capture_output=True, timeout=30)
    else:
        log('server reapply SKIPPED: upstream block changed, needs review')


OLD_BLOCK = """    case 'input':
      if (!inputMap[value]) return cb({ ok: false, error: 'unknown input' });
      return luna('com.webos.applicationManager/launch',
                  { id: 'com.webos.app.' + value },
                  function (r) { cb({ ok: !!(r && r.returnValue) }); });"""

NEW_BLOCK = """    case 'input':
      if (!inputMap[value]) return cb({ ok: false, error: 'unknown input' });
      return launchInputWithCec('com.webos.app.' + value, cb);"""

HELPERS = """
// Launching an HDMI input bare shows video but leaves CEC dead: the input
// app never learns the CEC device id, so remote keys stay local (OK just
// pops the input banner). The stock picker launches with
// params {id:'uniqueId', value:'<n>'}, taken from the launch-point table and
// falling back to eim's live device list. Reproduce that here, so API and
// Home Assistant input switches keep CEC control like the picker does.
function launchInputWithCec(appId, cb) {
  inputUniqueId(appId, function (uid) {
    var payload = { id: appId };
    if (uid > 0) payload.params = { id: 'uniqueId', value: String(uid) };
    return luna('com.webos.applicationManager/launch', payload, function (r) {
      cb({ ok: !!(r && r.returnValue) });
    });
  });
}

function inputUniqueId(appId, cb) {
  luna('com.webos.applicationManager/listLaunchPoints', {}, function (lp) {
    try {
      var pts = (lp && lp.launchPoints) || [];
      for (var i = 0; i < pts.length; i++) {
        if (pts[i].id === appId) {
          var p = pts[i].params || pts[i].extraInfo || {};
          if (parseInt(p.value, 10) > 0) return cb(parseInt(p.value, 10));
          break;
        }
      }
    } catch (e) {}
    luna('com.webos.service.eim/getAllInputStatus', {}, function (st) {
      try {
        var devs = (st && st.devices) || [];
        for (var j = 0; j < devs.length; j++) {
          var d = devs[j];
          var dApp = d.appId ||
            ('com.webos.app.' + String(d.id || '').toLowerCase().replace('_', ''));
          if (dApp === appId) {
            if (d.lastUniqueId > 0) return cb(d.lastUniqueId);
            var subs = d.subList || [];
            for (var k = 0; k < subs.length; k++) {
              if (subs[k].uniqueId > 0) return cb(subs[k].uniqueId);
            }
            break;
          }
        }
      } catch (e2) {}
      return cb(0);
    });
  });
}
"""


def cecfix_apply():
    path = '/var/lib/tvweb/lib/controls.js'
    with open(path) as f:
        src = f.read()
    if CECFIX_MARK in src:
        return True
    if OLD_BLOCK not in src:
        return False
    src = src.replace(OLD_BLOCK, NEW_BLOCK, 1)
    anchor = 'function num(v, dflt) {'
    idx = src.find(anchor)
    if idx < 0:
        return False
    end = src.find('}\n', idx) + len('}\n')
    src = src[:end] + HELPERS + src[end:]
    with open(path + '.bak-cecfix-auto', 'w') as f:
        f.write(open(path).read())
    with open(path, 'w') as f:
        f.write(src)
    return True


LP_OLD = """  if (pathname === '/api/hdmi') {
    return telemetryModule.hdmiInputs(function (r) { send(res, 200, JSON.stringify(r)); });
  }"""

LP_NEW = """  if (pathname === '/api/hdmi') {
    return telemetryModule.hdmiInputs(function (r) { send(res, 200, JSON.stringify(r)); });
  }

  // launchPointsApi: the home launcher's own tile order, with each tile's
  // title, icon and card color. Served for the overlay bar so it renders the
  // same row in the same order without duplicating launcher internals.
  // removable tells the bar whether the Uninstall menu item applies.
  if (pathname === '/api/launchpoints') {
    return lunaFn('com.webos.applicationManager/listLaunchPoints', {}, function (lp) {
      var pts = (lp && lp.launchPoints) || [];
      send(res, 200, JSON.stringify({ ok: true, points: pts.map(function (p) {
        return { id: p.id, title: p.title, iconColor: p.iconColor || '',
                 bgColor: p.bgColor || '', removable: !!p.removable,
                 params: p.params || p.extraInfo || null };
      }) }));
    });
  }"""


def lp_apply():
    path = '/var/lib/tvweb/lib/routes.js'
    with open(path) as f:
        src = f.read()
    if LP_MARK in src:
        return True
    if LP_OLD not in src:
        return False
    src = src.replace(LP_OLD, LP_NEW, 1)
    with open(path + '.bak-lpapi-auto', 'w') as f:
        f.write(open(path).read())
    with open(path, 'w') as f:
        f.write(src)
    return True


def main():
    os.makedirs('/var/lib/barwatcher', exist_ok=True)
    log('watcher start, event size %d' % EVT_SZ)
    cecfix_guard(force=True)
    poll = select.poll()
    fds = {}
    for path in sorted(glob.glob('/dev/input/event*')):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        fds[fd] = path
        poll.register(fd, select.POLLIN)
    log('watching %d input nodes' % len(fds))
    if not fds:
        return
    last = {}
    global _last_home_key, _last_any_key
    while True:
        try:
            cecfix_guard()
            track_fg()
            maybe_bounce()
            for fd, _ in poll.poll(1000):
                try:
                    data = os.read(fd, EVT_SZ * 32)
                except OSError:
                    continue
                for i in range(0, len(data) - EVT_SZ + 1, EVT_SZ):
                    _, _, typ, code, val = struct.unpack(EVT_FMT, data[i:i + EVT_SZ])
                    if typ != EV_KEY or val != 1:
                        continue
                    # Idle tracking ignores the proprietary (768+) range: the
                    # system synthesizes codes up there around app transitions
                    # (seen unpressed), and those phantoms must not veto the
                    # bounce. Genuine remote activity lives below 768 plus
                    # HOME/GREEN, and the fire-time foreground re-check backs
                    # this up regardless.
                    if code < 768 or code in (HOME_CODE, GREEN_CODE):
                        _last_any_key = time.time()
                    if code == HOME_CODE:
                        _last_home_key = _last_any_key
                    if code in (HOME_CODE, GREEN_CODE):
                        now = time.time()
                        if now - last.get(code, 0.0) < DEBOUNCE_S:
                            continue
                        last[code] = now
                        try:
                            on_key(code)
                        except Exception as e:
                            log('on_key failed: %s' % e)
                    elif code >= 768:
                        log('proprietary key code=%d' % code)
        except Exception as e:
            log('loop error: %s' % e)
            time.sleep(2)


if __name__ == '__main__':
    import sys
    if '--cecfix-only' in sys.argv:
        os.makedirs('/var/lib/barwatcher', exist_ok=True)
        try:
            cecfix_guard(force=True)
        except Exception as e:
            log('cecfix-only failed: %s' % e)
    else:
        main()
