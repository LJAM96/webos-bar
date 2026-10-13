# Revert

Everything here is reversible; nothing on the read-only rootfs was ever
modified (all changes are bind mounts, `/var/lib` files, or sideloaded apps).
A factory reset also wipes all of it, but that is never necessary — follow
the layers below.

## Just want stock Home back (keep the bar)?

```sh
rm -f /var/lib/webosbrew/init.d/48-nohome /var/lib/barwatcher/no-home
cp /var/lib/barwatcher/profile-baks/preload-conf.json.bak-homefix \
   /var/preferences/webos-preload-manager-conf.json 2>/dev/null
systemctl restart preload-manager 2>/dev/null || true
reboot
```

Without the hook and marker, Home renders normally again and HOME behaves
stock (except closing an open bar). The bar stays installed and GREEN keeps
working. The bounce logic stays armed but only fires on genuine strandings.

## Remove the bar app (keep watcher + patches)?

```sh
sh /tmp/lgtv-bar/tools/install-app.sh /tmp/lgtv-bar/barapp \
  com.lukemulvaney.bar 1.2.7 remove
```

(Stage this repo to `/tmp/lgtv-bar` first; `/tmp` is wiped every reboot.)
Then stop using GREEN (the watcher will log refusals harmlessly), or remove
the watcher too (below).

## Full removal (back to pre-bar state)

```sh
# 1. Bar app (needs the repo staged at /tmp/lgtv-bar; see above)
sh /tmp/lgtv-bar/tools/install-app.sh /tmp/lgtv-bar/barapp \
  com.lukemulvaney.bar 1.2.7 remove
# 2. Preload list (only if the no-home hook ever touched it — restore BEFORE
#    step 3 deletes the backup below with /var/lib/barwatcher)
cp /var/lib/barwatcher/profile-baks/preload-conf.json.bak-homefix \
   /var/preferences/webos-preload-manager-conf.json 2>/dev/null
systemctl restart preload-manager 2>/dev/null || true
# 3. Watcher (bracket form so pkill cannot match its own shell)
pkill -f '[b]arwatcher/watch.py'
rm -rf /var/lib/barwatcher
rm -f /var/lib/webosbrew/init.d/48-nohome \
      /var/lib/webosbrew/init.d/50-barwatcher \
      /var/lib/webosbrew/init.d/51-cecfix
# 3. Server patches (backups were taken at install time)
cp /var/lib/tvweb/lib/controls.js.bak-manual /var/lib/tvweb/lib/controls.js
cp /var/lib/tvweb/lib/routes.js.bak-manual /var/lib/tvweb/lib/routes.js
/var/lib/tvweb/tvwebctl restart
# 4. Live no-Home mounts, if active (reboot clears these anyway)
umount /usr/palm/applications/com.webos.app.home 2>/dev/null
for j in /mnt/lg/cmn_data/var/palm/jail/lg.thinqai.adapter/usr/palm/applications/com.webos.app.home \
         /mnt/lg/flash/data/var/palm/jail/lg.thinqai.adapter/usr/palm/applications/com.webos.app.home \
         /mnt/lg/user/var/palm/jail/lg.thinqai.adapter/usr/palm/applications/com.webos.app.home \
         /mnt/lg/cmn_data/var/palm/jail/com.webos.service.voice.performer/usr/palm/applications/com.webos.app.home \
         /mnt/lg/flash/data/var/palm/jail/com.webos.service.voice.performer/usr/palm/applications/com.webos.app.home \
         /mnt/lg/user/var/palm/jail/com.webos.service.voice.performer/usr/palm/applications/com.webos.app.home; do
  umount "$j" 2>/dev/null
done
luna-send -n 1 -f luna://com.webos.applicationManager/launch '{"id":"com.webos.app.home"}'
reboot
```

After the reboot: stock Home, stock keys, stock switching. tvweb itself is
untouched apart from its two restored files.

## Emergency recovery

If the UI ever wedges and SSH still answers: `umount` the Home path above,
kill the watcher with the bracket-form pkill, and `reboot`. If SSH is down
too, pull power: every bind mount and marker that matters is transient
except `/var/lib` files, which are inert without their hooks (and the hooks
only run clean, guarded code paths).
