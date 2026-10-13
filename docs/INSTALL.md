# Install from scratch

Prerequisites: rooted LG webOS TV with Homebrew Channel (SSH `root@<tv-ip>`,
password `alpine` unless keys are set up), the tvweb server deployed and
answering on `:8080`, and this directory staged on the TV (e.g. under
`/tmp/lgtv-bar` — note `/tmp` is wiped every reboot, so stage fresh).

All TV-side commands run as root over SSH.

## 1. Server patches

Back up, copy, syntax-check with the TV's own node, restart:

```sh
cp /var/lib/tvweb/lib/controls.js /var/lib/tvweb/lib/controls.js.bak-manual
cp /var/lib/tvweb/lib/routes.js /var/lib/tvweb/lib/routes.js.bak-manual
# copy server-patches/controls.js -> /var/lib/tvweb/lib/controls.js
# copy server-patches/routes.js   -> /var/lib/tvweb/lib/routes.js
node -e "new (require('vm').Script)(require('fs').readFileSync('/var/lib/tvweb/lib/controls.js','utf8')); console.log('controls ok')"
node -e "new (require('vm').Script)(require('fs').readFileSync('/var/lib/tvweb/lib/routes.js','utf8')); console.log('routes ok')"
# ('node --check' misfires on this build; the vm.Script form above is the check.)
/var/lib/tvweb/tvwebctl restart
sleep 4; /var/lib/tvweb/tvwebctl status
curl -s http://127.0.0.1:8080/api/launchpoints | head -c 200  # expect ok:true
```

Verify CEC switching: POST `/api/control {"action":"input","value":"hdmi4"}`
from an input, then confirm `DEEPLINK CEC uniqueId <n>` (n > 0) in
`/var/log/inputcommon` and remote control of the box.

## 2. Bar app

Packaged and installed on the TV exactly like the tvweb dashboard app (ar
archive by hand, `com.webos.appInstallService/dev/install`), via
`tools/install-app.sh` (runs on the TV):

```sh
sh /tmp/lgtv-bar/tools/install-app.sh /tmp/lgtv-bar/barapp \
  com.lukemulvaney.bar 1.2.7 install Bar
```

Launch once and check the bar renders over video:

```sh
luna-send -n 1 -f luna://com.webos.applicationManager/launch '{"id":"com.lukemulvaney.bar"}'
```

Bump the version argument on every reinstall so installs are distinguishable
(the number is packaging metadata only; the app reads no version of itself).

## 3. Watcher + boot hooks

```sh
mkdir -p /var/lib/barwatcher
cp /tmp/lgtv-bar/watcher/watch.py /tmp/lgtv-bar/watcher/boot-input.py \
   /var/lib/barwatcher/
cp /tmp/lgtv-bar/watcher/48-nohome /tmp/lgtv-bar/watcher/50-barwatcher \
   /tmp/lgtv-bar/watcher/51-cecfix /var/lib/webosbrew/init.d/
chmod 755 /var/lib/webosbrew/init.d/48-nohome \
          /var/lib/webosbrew/init.d/50-barwatcher \
          /var/lib/webosbrew/init.d/51-cecfix
python3 -c "import ast; ast.parse(open('/var/lib/barwatcher/watch.py').read()); print('ok')"
python3 -c "import ast; ast.parse(open('/var/lib/barwatcher/boot-input.py').read()); print('ok')"
sh -n /var/lib/webosbrew/init.d/48-nohome && echo hook-ok
setsid /usr/bin/python3 /var/lib/barwatcher/watch.py </dev/null >>/var/lib/barwatcher/watch.log 2>&1 &
```

To enter no-Home standard live without rebooting: bind an empty dir over
`/usr/palm/applications/com.webos.app.home`, kill the flutter Home renderer
(bracket-form pkill so it cannot match its own shell:
`pkill -f '[f]lutter.*app.home'`), `touch /var/lib/barwatcher/no-home`.
A reboot with the hooks installed does all of this automatically.

## 4. Verify

- Cold boot lands on the last input by itself; `watch.log` shows
  `nohome boot settled` (fast path) and no Home renderer appears.
- GREEN raises the bar over inputs and over apps; GREEN again closes it;
  10s idle closes it.
- HOME raises the bar directly, never full Home.
- Backing out of an app strands ~2s, then video returns alone; pressing any
  key on the strand cancels the bounce.
- Tile switch keeps CEC control of the box (arrows/OK, no banner on OK).
- Edit mode hides/reorders and persists across reopen.
- Hold OK on a tile opens its menu: force close, move, hide, uninstall
  (uninstall only on removable apps, two taps to confirm).
- `/var/lib/barwatcher/watch.log` has no `on_key failed` or guard errors.
