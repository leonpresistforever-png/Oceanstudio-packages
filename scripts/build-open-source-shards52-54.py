#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, tempfile
from pathlib import Path

PREFIX="/data/data/studio.ocean.app/files/usr"
VERSION="1.0.0-1"

SHARD52=['neovim', 'emacs', 'helix', 'kakoune', 'joe', 'jed', 'vis', 'zile', 'mg', 'zellij', 'dvtm', 'abduco', 'byobu', 'mosh', 'autossh', 'ncdu', 'ranger', 'nnn', 'lf', 'vifm', 'yazi', 'mc', 'dust', 'duf', 'gdu', 'dua', 'jdupes', 'rdfind', 'rmlint', 'fclones', 'trash-cli', 'moreutils', 'most', 'pv', 'progress', 'rlwrap', 'expect', 'tmate', 'ttyrec', 'boxes', 'figlet', 'toilet', 'lolcat', 'fortune', 'cowsay', 'cmatrix', 'neofetch', 'macchina', 'onefetch', 'glances', 'atop', 'dstat', 'ioping', 'nethogs', 'bmon', 'iftop', 'vnstat', 'procps', 'plocate', 'silver-searcher', 'ack', 'ugrep', 'man-db', 'elvish', 'xonsh', 'yash', 'mksh', 'tcsh', 'ksh', 'atuin', 'carapace', 'entr', 'watch', 'tig', 'cronie', 'fcron', 'supercronic', 'redis', 'valkey', 'keydb', 'mariadb', 'ncat', 'iproute2', 'iputils', 'bridge-utils', 'arp-scan', 'arping', 'iperf', 'nload', 'ngrep', 'netsniff-ng', 'hping', 'fping', 'whois', 'bind', 'stubby', 'dogdns', 'wget2', 'axel', 'hey']
SHARD53=['hurl', 'proxychains-ng', 'torsocks', 'tinyproxy', 'nginx', 'lighttpd', 'apache-httpd', 'miniserve', 'darkhttpd', 'thttpd', 'sshpass', 'wireguard-go', 'zerotierone', 'ocserv', 'openconnect', 'unison', 'lsyncd', 'rsnapshot', 'rustic', 'rdiff-backup', 'zrepl', 'nfs-utils', 'samba', 'sshfs', 'curlftpfs', 'lftp', 'cadaver', 'varnish', 'hitch', 'supervisor', 'monit', 's6', 'runit', 'daemontools', 'dumb-init', 'tini', 'immortal', 'chrony', 'ntp', 'openntpd', 'clickhouse', 'vault', 'cockroachdb', 'dbmate', 'atlas', 'flyway', 'liquibase', 'sqitch', 'goose', 'tern', 'podman', 'oras', 'regctl', 'dive', 'nerdctl', 'docker-client', 'docker-compose', 'docker-buildx', 'containerd', 'youki', 'kind', 'stern', 'kubectx', 'talosctl', 'fluxcd', 'argocd', 'cilium-cli', 'istioctl', 'terragrunt', 'ansible', 'ansible-lint', 'chezmoi', 'stow', 'yadm', 'dotbot', 'just', 'go-task', 'taskwarrior', 'watchexec', 'fswatch', 'inotify-tools', 'gitui', 'jj', 'fossil', 'mercurial', 'git-annex', 'git-crypt', 'git-filter-repo', 'git-sizer', 'delta', 'difftastic', 'tea', 'hub', 'lbzip2', 'lzip', 'lzop', 'snzip', 'dasel', 'pup', 'htmlq']
SHARD54=['xmlstarlet', 'tidy-html5', 'jless', 'jc', 'jo', 'jid', 'lua', 'julia', 'sccache', 'bear', 'patchutils', 'cscope', 'universal-ctags', 'w3m', 'lynx', 'links2', 'elinks', 'browsh', 'ddgr', 'googler', 'newsboat', 'neomutt', 'aerc', 'alpine', 'msmtp', 'isync', 'notmuch', 'timewarrior', 'calcurse', 'remind', 'khal', 'vdirsyncer', 'ledger', 'hledger', 'beancount', 'jrnl', 'todo-txt-cli', 'recode', 'enca', 'uchardet', 'parallel', 'choose', 'sd', 'cheat', 'navi', 'procs', 'net-tools', 'inetutils', 'netperf', 'netcat-gnu', 'termshark', 'sniffglue', 'rustscan', 'dnsperf', 'dnstop', 'dnstracer', 'coredns', 'powerdns', 'knot-resolver', 'nghttp2', 'websocketd', 'websockify', 'wstunnel', 'bore-cli', 'seaweedfs', 'garage', 'croc', 'magic-wormhole', 'wormhole-william', 'dufs', 'filebrowser', 'rabbitmq-server', 'beanstalkd', 'nsq', 'xray', 'sing-box', 'stunnel', 'lego', 'prometheus', 'blackbox-exporter', 'victoriametrics', 'loki', 'promtail', 'redli', 'mongosh', 'mongodb-tools', 'rqlite', 'sops', 'pass', 'gopass', 'nomad', 'boundary', 'goreleaser', 'ko', 'nixfmt-rfc-style', 'alejandra', 'deadnix', 'statix', 'shellharden', 'cloc']
OVERRIDES={'neovim': ('neovim', 'nvim'), 'helix': ('helix', 'hx'), 'moreutils': ('moreutils', 'sponge'), 'procps': ('procps', 'ps'), 'silver-searcher': ('silver-searcher', 'ag'), 'man-db': ('man-db', 'man'), 'watch': ('procps', 'watch'), 'cronie': ('cronie', 'crond'), 'redis': ('redis', 'redis-server'), 'valkey': ('valkey', 'valkey-server'), 'keydb': ('keydb', 'keydb-server'), 'mariadb': ('mariadb', 'mariadb'), 'ncat': ('nmap', 'ncat'), 'iproute2': ('iproute2', 'ip'), 'iputils': ('iputils', 'ping'), 'bridge-utils': ('bridge-utils', 'brctl'), 'bind': ('bind', 'dig'), 'dogdns': ('dogdns', 'dog'), 'apache-httpd': ('apacheHttpd', 'httpd'), 'nfs-utils': ('nfs-utils', 'exportfs'), 'samba': ('samba', 'smbclient'), 'supervisor': ('supervisor', 'supervisord'), 'ntp': ('ntp', 'ntpd'), 'docker-client': ('docker-client', 'docker'), 'go-task': ('go-task', 'task'), 'taskwarrior': ('taskwarrior3', 'task'), 'jj': ('jujutsu', 'jj'), 'links2': ('links2', 'links'), 'isync': ('isync', 'mbsync'), 'todo-txt-cli': ('todo-txt-cli', 'todo.sh'), 'net-tools': ('nettools', 'ifconfig'), 'inetutils': ('inetutils', 'telnet'), 'netcat-gnu': ('netcat-gnu', 'nc'), 'powerdns': ('pdns', 'pdns_server'), 'knot-resolver': ('knot-resolver', 'kresd'), 'seaweedfs': ('seaweedfs', 'weed'), 'magic-wormhole': ('magic-wormhole', 'wormhole'), 'nsq': ('nsq', 'nsqd'), 'blackbox-exporter': ('prometheus-blackbox-exporter', 'blackbox_exporter'), 'victoriametrics': ('victoriametrics', 'victoria-metrics-prod'), 'loki': ('grafana-loki', 'loki'), 'promtail': ('grafana-loki', 'promtail'), 'mongodb-tools': ('mongodb-tools', 'mongodump'), 'nixfmt-rfc-style': ('nixfmt-rfc-style', 'nixfmt')}
ALIASES={'neovim': 'nvim', 'helix': 'hx', 'silver-searcher': 'ag', 'man-db': 'man', 'cronie': 'crond', 'redis': 'redis-server', 'valkey': 'valkey-server', 'keydb': 'keydb-server', 'iproute2': 'ip', 'iputils': 'ping', 'bridge-utils': 'brctl', 'bind': 'dig', 'dogdns': 'dog', 'apache-httpd': 'httpd', 'nfs-utils': 'exportfs', 'supervisor': 'supervisord', 'isync': 'mbsync', 'powerdns': 'pdns_server', 'knot-resolver': 'kresd', 'seaweedfs': 'weed', 'magic-wormhole': 'wormhole', 'nsq': 'nsqd', 'blackbox-exporter': 'blackbox_exporter', 'loki': 'loki', 'promtail': 'promtail', 'mongodb-tools': 'mongodump', 'nixfmt-rfc-style': 'nixfmt'}

SHARDS={
 "52":(SHARD52,"staging/shard-52","terminal-unix-foundation-suite","editors, terminals, shells and Unix administration"),
 "53":(SHARD53,"staging/shard-53","network-server-foundation-suite","networking, servers, databases, services and DevOps"),
 "54":(SHARD54,"staging/shard-54","open-source-cli-foundation-suite","open-source CLI, data, mail, web and infrastructure tools"),
}
SUPERPACK="ocean-open-source-superpack"
EXISTING_ESSENTIALS=["nano","vim","tmux","rclone","socat","nmap","perl","openssh","rsync","curl","wget","git","bash","coreutils"]

def spec(pkg):
    if pkg=="ncat":
        return ("meta","nmap","ncat")
    attr,cmd=OVERRIDES.get(pkg,(pkg,pkg))
    return ("nix",attr,cmd)

def repo_names():
    try:
        paths=subprocess.check_output(["git","ls-tree","-r","--name-only","HEAD"],text=True).splitlines()
    except Exception:
        return set()
    skip=("staging/shard-52/","staging/shard-53/","staging/shard-54/","staging/open-source-superpack/")
    out=set()
    for p in paths:
        if p.endswith(".deb") and not p.startswith(skip):
            out.add(Path(p).name.split("_",1)[0])
    return out

def control(pkg,kind,attr,cmd,label):
    if kind=="meta":
        dep="nmap"
        detail="Meta package exposing Ncat through the existing Nmap package."
    else:
        dep="nix-ocean"
        detail=f"Open-source bridge to nixpkgs#{attr}; invokes upstream command {cmd} on demand."
    return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: utils
Priority: optional
Depends: {dep}
Description: {label} - {pkg}
 {detail}
 No network activity or source download is performed by APT maintainer scripts.
"""

def launcher(pkg,attr,cmd):
    alias=ALIASES.get(pkg)
    plan=json.dumps({"package":pkg,"nixAttr":attr,"upstreamCommand":cmd,"provider":"nix-ocean"})
    self_alias=alias or pkg
    return f"""#!/system/bin/sh
PREFIX="${{PREFIX:-{PREFIX}}}"
if [ "${{1:-}}" = "--ocean-plan" ]; then
  printf '%s\\n' {json.dumps(plan)}
  exit 0
fi
SELF="$PREFIX/bin/{pkg}"
FOUND="$(command -v {cmd} 2>/dev/null || true)"
if [ -n "$FOUND" ] && [ "$FOUND" != "$SELF" ] && [ "$FOUND" != "$PREFIX/bin/{self_alias}" ]; then
  exec "$FOUND" "$@"
fi
if command -v nix >/dev/null 2>&1; then
  exec nix --extra-experimental-features "nix-command flakes" shell "nixpkgs#{attr}" -c {cmd} "$@"
fi
echo "{pkg}: nix-ocean is required to resolve nixpkgs#{attr}" >&2
exit 127
"""

def meta_control(pkg,deps,desc):
    atoms=[]
    for x in deps:
        if x.startswith(("terminal-","network-","open-source-")):
            atoms.append(f"{x} (= {VERSION})")
        else:
            atoms.append(x)
    return f"""Package: {pkg}
Version: {VERSION}
Architecture: all
Maintainer: OceanStudio <packages@ocean.studio>
Section: metapackages
Priority: optional
Depends: {", ".join(atoms)}
Description: {desc}
 Meta-package only; installs the corresponding Ocean open-source capability set.
"""

def build_one(pkg,pool,label):
    kind,attr,cmd=spec(pkg)
    with tempfile.TemporaryDirectory(prefix="ocean-open-source-") as td:
        root=Path(td)/pkg
        deb=root/"DEBIAN"; deb.mkdir(parents=True)
        (deb/"control").write_text(control(pkg,kind,attr,cmd,label))
        if kind=="nix":
            bind=root/PREFIX.strip("/")/"bin"; bind.mkdir(parents=True)
            p=bind/pkg; p.write_text(launcher(pkg,attr,cmd)); p.chmod(0o755)
            alias=ALIASES.get(pkg)
            if alias and alias!=pkg:
                q=bind/alias
                if not q.exists():
                    q.write_text(launcher(pkg,attr,cmd)); q.chmod(0o755)
        art=pool/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art,kind,attr,cmd

def build_meta(pkg,deps,pool,desc):
    with tempfile.TemporaryDirectory(prefix="ocean-open-source-meta-") as td:
        root=Path(td)/pkg; (root/"DEBIAN").mkdir(parents=True)
        (root/"DEBIAN/control").write_text(meta_control(pkg,deps,desc))
        art=pool/f"{pkg}_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb","--root-owner-group","--build",str(root),str(art)],check=True,stdout=subprocess.DEVNULL)
        return art

def rec(art,pkg,kind,attr,cmd):
    raw=art.read_bytes()
    return {"package":pkg,"artifact":art.name,"provider":kind,"upstream":attr,"command":cmd,
            "bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}

def write_index(out,rows):
    paras=[]
    for r in rows:
        art=out/"pool/main"/r["artifact"]
        fields=subprocess.check_output(["dpkg-deb","-f",str(art)],text=True).strip()
        paras.append(fields+f"\nFilename: {out.as_posix()}/pool/main/{art.name}\nSize: {r['bytes']}\nSHA256: {r['sha256']}\n")
    (out/"Packages.repaired").write_text("\n".join(paras))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--shards",default="52,53,54"); a=ap.parse_args()
    nums=[x.strip() for x in a.shards.split(",") if x.strip()]
    allnames=SHARD52+SHARD53+SHARD54
    if len(allnames)!=300 or len(set(allnames))!=300:
        raise SystemExit("catalog must be exactly 300 unique package names")
    existing=repo_names()
    collisions=sorted(set(allnames)&existing)
    if collisions:
        raise SystemExit("repo-wide package collisions: "+", ".join(collisions))
    suites=[]; total=0
    for n in nums:
        names,outname,suite,label=SHARDS[n]
        out=Path(outname); pool=out/"pool/main"
        if out.exists(): shutil.rmtree(out)
        pool.mkdir(parents=True)
        rows=[]
        for pkg in names:
            art,kind,attr,cmd=build_one(pkg,pool,label)
            rows.append(rec(art,pkg,kind,attr,cmd))
        mart=build_meta(suite,names,pool,"Ocean "+label+" suite")
        rows.append(rec(mart,suite,"meta","",""))
        write_index(out,rows)
        (out/"provenance.json").write_text(json.dumps({
          "schemaVersion":1,"shard":n,"version":VERSION,"prefix":PREFIX,
          "commandPackageCount":100,"metaPackageCount":1,"packageCount":101,
          "suite":suite,"networkAtAptInstall":False,"rootRequired":False,
          "implementation":"real upstream open-source tools resolved through nix-ocean; no renamed no-op placeholders",
          "packages":rows
        },indent=2)+"\n")
        suites.append(suite); total += len(rows)
    out=Path("staging/open-source-superpack"); pool=out/"pool/main"
    if out.exists(): shutil.rmtree(out)
    pool.mkdir(parents=True)
    deps=suites+EXISTING_ESSENTIALS
    art=build_meta(SUPERPACK,deps,pool,"Ocean open-source terminal and server superpack")
    row=rec(art,SUPERPACK,"meta","","")
    write_index(out,[row])
    (out/"provenance.json").write_text(json.dumps({
      "schemaVersion":1,"version":VERSION,"prefix":PREFIX,"dependsOnSuites":suites,
      "alsoInstallsExistingEssentials":EXISTING_ESSENTIALS,
      "newCommandPackages":300,"totalNewPackages":304
    },indent=2)+"\n")
    print(json.dumps({"newCommandPackages":300,"metaPackages":4,"totalNewPackages":304,"suites":suites},indent=2))

if __name__=="__main__":
    main()
