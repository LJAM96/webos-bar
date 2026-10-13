# lgtv-bar — no-Home overlay launcher for a rooted LG webOS TV

The TV runs a **no-Home standard**: the stock Home app is hidden at boot,
and a transparent overlay bar replaces it. GREEN raises the bar over whatever
is playing; HOME raises it too. Backing out of an app returns to the last
input by itself. Input switching preserves HDMI-CEC control.

## Environment

| Item | Value |
|---|---|
| TV | LG OLED65B42LA, webOS 10.2.2, firmware 33.22.75 |
| TV address | 192.168.31.162, SSH `root` / `alpine` |
| Glasshouse tvweb server | 0.73.2 at `/var/lib/tvweb`, dashboard on `:8080` |
| Bar app | `com.lukemulvaney.bar` v1.2.7 |
| Remote codes (this remote) | HOME 773, GREEN 399, Back 412 |

## Components

| Directory | Deploys to | Purpose |
|---|---|---|
| `barapp/` | Home-screen app via dev-install service | Transparent overlay tile bar |
| `watcher/watch.py` | `/var/lib/barwatcher/watch.py`, always running | Key watcher, bounce recovery, patch guard |
| `watcher/boot-input.py` | `/var/lib/barwatcher/boot-input.py` | CEC-safe input switch without tvweb |
| `watcher/boot-input.py` | `/var/lib/barwatcher/boot-input.py` | CEC-safe input switch without tvweb |
| `watcher/48-nohome` | `/var/lib/webosbrew/init.d/48-nohome` | Boot: hide Home, mark no-home, boot to input |
| `watcher/50-barwatcher` | `/var/lib/webosbrew/init.d/50-barwatcher` | Boot: start the watcher |
| `watcher/51-cecfix` | `/var/lib/webosbrew/init.d/51-cecfix` | Boot: reapply server patches if wiped |
| `server-patches/` | `/var/lib/tvweb/lib/` | CEC-aware input switching, launchpoints API |
| `tools/install-app.sh` | run on TV | Package + dev-install a webOS app from a dir |

Live checksums (all verified against the TV):

```
540ce283409d550278a079ac96118bbe  barapp/index.html
4599848b9e4656821ae985dd3635711a  barapp/appinfo.json
ab1a3ef41e1b33fe18d90c92d9827514  barapp/packageinfo.json
dc7a67f939bb683812653d0f78b7281c  watcher/watch.py
3a3ecf34862729bda046d50f3c145489  watcher/boot-input.py
237dc13430bfff9c3b83f4a3a82db6f4  watcher/48-nohome
f7d0c5ba0b51afde27f579fb32275716  watcher/50-barwatcher
b99242cd7b4f8765662a78637dcfe0a9  watcher/51-cecfix
f58e7d22c5698904b613266a7f5b098b  server-patches/controls.js
6237a0a9d53da8b283154bad85d7220a  server-patches/routes.js
77d35be8326f6fa1d721b699d26e44d7  tools/install-app.sh
```

Watcher files evolve with tuning; re-verify at each deploy (see INSTALL).

## Quick operations (run on the TV over SSH)

```sh
# Watcher status + recent activity
ps aux | grep '[b]arwatcher/watch.py'
tail -n 20 /var/lib/barwatcher/watch.log
# tvweb status
/var/lib/tvweb/tvwebctl status
# Relaunch the bar / close it
luna-send -n 1 -f luna://com.webos.applicationManager/launch '{"id":"com.lukemulvaney.bar"}'
luna-send -n 1 -f luna://com.webos.applicationManager/closeByAppId '{"id":"com.lukemulvaney.bar"}'
# Restart the watcher (note: pkill pattern must not match its own shell)
pkill -f '[b]arwatcher/watch.py'
setsid /usr/bin/python3 /var/lib/barwatcher/watch.py </dev/null >>/var/lib/barwatcher/watch.log 2>&1 &
```

## Docs

- `docs/ARCHITECTURE.md` — how it all works
- `docs/INSTALL.md` — reinstall from scratch
- `docs/REVERT.md` — remove everything, back to stock behavior
- `docs/MAINTENANCE.md` — updates, tuning, troubleshooting
