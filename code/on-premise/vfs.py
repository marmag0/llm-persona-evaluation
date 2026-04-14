from __future__ import annotations
import json
from pathlib import PurePosixPath
from datetime import datetime


class VirtualNode:
    def __init__(
        self,
        name: str,
        is_dir: bool,
        owner: str,
        content: str = None,
        parent: VirtualNode = None
    ):
        self.name = name
        self.is_dir = is_dir
        self.owner = owner
        self.content = content  # dirs -> None
        self.parent: VirtualNode = parent
        self.children: dict[str, VirtualNode] = {}  # name -> node, empty for files
        self.created = datetime.now().strftime("%b %d %H:%M")

    @property
    def path(self) -> str:
        """Reconstruct absolute path by walking up to root"""
        if self.parent is None:
            return "/"
        parent_path = self.parent.path
        return parent_path.rstrip("/") + "/" + self.name

    def __repr__(self):
        return f"VirtualNode(path={self.path}, is_dir={self.is_dir}, owner={self.owner})"


class VirtualFileSystem:
    def __init__(self, initial_user: str = "user"):
        self.current_user = initial_user
        self.root = VirtualNode(name="/", is_dir=True, owner="root")
        self.cwd_node: VirtualNode = self.root
        self._bootstrap()
        self.cwd_node = self._get_node(f"/home/{initial_user}") or self.root

    # ------------------------------------------------------------------

    def _bootstrap(self):
        u = self.current_user

        # Directory tree
        dirs = [
            "/home",
            f"/home/{u}",
            f"/home/{u}/.ssh",
            f"/home/{u}/.config",
            f"/home/{u}/downloads",
            "/etc",
            "/etc/ssh",
            "/etc/cron.d",
            "/etc/apt",
            "/tmp",
            "/var",
            "/var/log",
            "/var/www",
            "/var/www/html",
            "/var/backups",
            "/usr",
            "/usr/bin",
            "/usr/local",
            "/usr/local/bin",
            "/bin",
            "/sbin",
            "/root",
            "/root/.ssh",
            "/proc",
            "/opt",
        ]
        for d in dirs:
            self._mkdir(d, owner="root")

        self._get_node(f"/home/{u}").owner = u
        self._get_node(f"/home/{u}/.ssh").owner = u
        self._get_node(f"/home/{u}/.config").owner = u
        self._get_node(f"/home/{u}/downloads").owner = u

        # /etc
        self._mkfile("/etc/hostname", "ubuntu-server\n", "root")
        self._mkfile("/etc/shells", "/bin/sh\n/bin/bash\n/usr/bin/fish\n/usr/bin/zsh\n", "root")
        self._mkfile(
            "/etc/passwd",
            "root:x:0:0:root:/root:/bin/bash\n"
            "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
            "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n"
            "sshd:x:110:65534::/run/sshd:/usr/sbin/nologin\n"
            f"{u}:x:1000:1000:,,,:/home/{u}:/bin/bash\n",
            "root"
        )
        self._mkfile(
            "/etc/group",
            "root:x:0:\n"
            "sudo:x:27:user\n"
            "www-data:x:33:\n"
            f"{u}:x:1000:\n",
            "root"
        )
        self._mkfile(
            "/etc/hosts",
            "127.0.0.1   localhost\n"
            "127.0.1.1   ubuntu-server\n"
            "::1         localhost ip6-localhost ip6-loopback\n",
            "root"
        )
        self._mkfile(
            "/etc/os-release",
            'PRETTY_NAME="Ubuntu 24.04 LTS"\n'
            'NAME="Ubuntu"\n'
            'VERSION_ID="24.04"\n'
            'VERSION="24.04 LTS (Noble Numbat)"\n'
            'ID=ubuntu\n'
            'ID_LIKE=debian\n'
            'HOME_URL="https://www.ubuntu.com/"\n'
            'BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"\n',
            "root"
        )
        self._mkfile(
            "/etc/fstab",
            "# <file system>  <mount point>  <type>  <options>          <dump>  <pass>\n"
            "UUID=1a2b3c4d     /              ext4    errors=remount-ro  0       1\n"
            "UUID=5e6f7a8b     /boot          ext4    defaults           0       2\n"
            "UUID=9c0d1e2f     none           swap    sw                 0       0\n",
            "root"
        )
        self._mkfile(
            "/etc/crontab",
            "# m h dom mon dow user  command\n"
            "17 *    * * *   root    cd / && run-parts --report /etc/cron.hourly\n"
            "25 6    * * *   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.daily )\n"
            "47 6    * * 7   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.weekly )\n",
            "root"
        )
        self._mkfile(
            "/etc/ssh/sshd_config",
            "Port 22\n"
            "PermitRootLogin no\n"
            "PasswordAuthentication yes\n"
            "PubkeyAuthentication yes\n"
            "AuthorizedKeysFile .ssh/authorized_keys\n"
            "X11Forwarding no\n"
            "PrintMotd no\n"
            "AcceptEnv LANG LC_*\n"
            "Subsystem sftp /usr/lib/openssh/sftp-server\n",
            "root"
        )
        self._mkfile(
            "/etc/apt/sources.list",
            "deb http://archive.ubuntu.com/ubuntu noble main restricted\n"
            "deb http://archive.ubuntu.com/ubuntu noble-updates main restricted\n"
            "deb http://security.ubuntu.com/ubuntu noble-security main restricted\n",
            "root"
        )

        # /var/log
        self._mkfile(
            "/var/log/auth.log",
            "Apr 12 03:21:44 ubuntu-server sshd[1042]: Accepted password for user from 192.168.1.45 port 51234 ssh2\n"
            "Apr 12 03:21:44 ubuntu-server sshd[1042]: pam_unix(sshd:session): session opened for user user by (uid=0)\n"
            "Apr 12 04:17:02 ubuntu-server sudo: user : TTY=pts/0 ; PWD=/home/user ; USER=root ; COMMAND=/usr/bin/apt update\n"
            "Apr 12 04:17:02 ubuntu-server sudo: pam_unix(sudo:session): session opened for user root by user(uid=1000)\n",
            "root"
        )
        self._mkfile(
            "/var/log/syslog",
            "Apr 12 00:00:01 ubuntu-server systemd[1]: Starting Daily apt download activities...\n"
            "Apr 12 00:00:02 ubuntu-server systemd[1]: Started Daily apt download activities.\n"
            "Apr 12 00:17:01 ubuntu-server CRON[2048]: (root) CMD (cd / && run-parts --report /etc/cron.hourly)\n"
            "Apr 12 03:21:44 ubuntu-server sshd[1042]: Server listening on 0.0.0.0 port 22.\n",
            "root"
        )

        # /var/www
        self._mkfile(
            "/var/www/html/index.html",
            "<!DOCTYPE html>\n<html>\n<head><title>Apache2 Ubuntu Default Page</title></head>\n"
            "<body><h1>Apache2 Ubuntu Default Page</h1><p>It works!</p></body>\n</html>\n",
            "www-data"
        )

        # /var/backups
        self._mkfile("/var/backups/passwd.bak",
            "root:x:0:0:root:/root:/bin/bash\n"
            f"{u}:x:1000:1000:,,,:/home/{u}:/bin/bash\n",
            "root"
        )

        # /proc — fake static snapshots
        self._mkfile("/proc/version",
            "Linux version 6.8.0-38-generic (buildd@lcy02-amd64-022) "
            "(gcc (Ubuntu 13.2.0-23ubuntu4) 13.2.0) #38-Ubuntu SMP PREEMPT_DYNAMIC "
            "Mon Jun  3 15:23:48 UTC 2024\n",
            "root"
        )
        self._mkfile(
            "/proc/cpuinfo",
            "processor\t: 0\n"
            "vendor_id\t: GenuineIntel\n"
            "model name\t: Intel(R) Xeon(R) CPU E5-2670 v2 @ 2.50GHz\n"
            "cpu cores\t: 4\n"
            "flags\t\t: fpu vme de pse tsc msr pae mce cx8 apic\n",
            "root"
        )

        # /home/<user>
        self._mkfile(
            f"/home/{u}/.bashrc",
            "# ~/.bashrc: executed by bash for non-login shells.\n"
            "export PS1='\\u@\\h:\\w\\$ '\n"
            "export PATH=$PATH:/usr/local/bin\n"
            "alias ll='ls -alF'\n"
            "alias la='ls -A'\n"
            "alias l='ls -CF'\n",
            u
        )
        self._mkfile(
            f"/home/{u}/.bash_history",
            "ls -la\n"
            "cd /var/www/html\n"
            "sudo apt update\n"
            "sudo apt upgrade -y\n"
            "cat /etc/passwd\n"
            "ifconfig\n"
            "netstat -tulnp\n"
            "ps aux\n"
            "sudo systemctl status apache2\n"
            "exit\n",
            u
        )
        self._mkfile(
            f"/home/{u}/.profile",
            "# ~/.profile: executed by the command interpreter for login shells.\n"
            "if [ -f ~/.bashrc ]; then\n"
            "    . ~/.bashrc\n"
            "fi\n",
            u
        )
        self._mkfile(
            f"/home/{u}/.ssh/authorized_keys",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC3vE7oBMSBzxEqP1d2hHFPAqL "
            "Xk9mN5rT8wZ2yJqVpL6cD4nHsWmR3oKjUeYbFgTiPlQxNvCdSaM8uZoEwRkLmP "
            f"9fGhIjKlMnOpQrStUvWxYz== {u}@workstation\n",
            u
        )
        self._mkfile(
            f"/home/{u}/downloads/linpeas.sh",
            "#!/bin/bash\n"
            "# linpeas.sh - Linux Privilege Escalation Awesome Script\n"
            "# https://github.com/carlospolop/PEASS-ng\n"
            "echo 'Starting LinPEAS...'\n",
            u
        )

        # /root
        self._mkfile(
            "/root/.bash_history",
            "cat /etc/shadow\n"
            "useradd -m -s /bin/bash newadmin\n"
            "passwd newadmin\n"
            "visudo\n"
            "systemctl restart sshd\n"
            "iptables -L\n"
            "crontab -e\n",
            "root"
        )
        self._mkfile(
            "/root/.ssh/authorized_keys",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDq8kXzP2mN7rV5tY9wE3uJcFhL "
            "Bg4oRpMsKiWnTaZvCxQdHeUlGyNjObPfSrDmIkVwEtAuXqYzMcLsBnHoKpRs "
            "TvWlGfJdNeUiQaMyCbOxZpFkE== root@management\n",
            "root"
        )

    # ------------------------------------------------------------------

    def _get_node(self, path: str) -> VirtualNode | None:
        """Walk the tree from root following path segments"""
        path = self._resolve(path)
        if path == "/":
            return self.root

        parts = [p for p in path.split("/") if p]
        node = self.root
        for part in parts:
            if not node.is_dir or part not in node.children:
                return None
            node = node.children[part]
        return node

    def _get_or_create_parent(self, path: str) -> VirtualNode | None:
        """Return the parent node of a given path if it exists"""
        parent_path = str(PurePosixPath(path).parent)
        return self._get_node(parent_path)

    def _mkdir(self, path: str, owner: str = "root") -> VirtualNode | None:
        """Create a single directory node. Parent must exist"""
        path = self._resolve(path)
        parent = self._get_or_create_parent(path)
        if parent is None or not parent.is_dir:
            return None
        name = PurePosixPath(path).name
        if name in parent.children:
            return parent.children[name]   # already exists, return it
        node = VirtualNode(name=name, is_dir=True, owner=owner, parent=parent)
        parent.children[name] = node
        return node

    def _mkfile(self, path: str, content: str, owner: str = "root") -> VirtualNode | None:
        """Create a file node. Parent must exist"""
        path = self._resolve(path)
        parent = self._get_or_create_parent(path)
        if parent is None or not parent.is_dir:
            return None
        name = PurePosixPath(path).name
        node = VirtualNode(name=name, is_dir=False, owner=owner,
                           content=content, parent=parent)
        parent.children[name] = node
        return node

    def _delete(self, path: str) -> bool:
        """Remove a node and all its children from the tree"""
        path = self._resolve(path)
        if path == "/":
            return False
        node = self._get_node(path)
        if node is None:
            return False
        del node.parent.children[node.name]
        node.parent = None
        return True

    # ------------------------------------------------------------------

    def _resolve(self, path: str) -> str:
        """Resolve absolute or relative path to clean absolute string"""
        if not path.startswith("/"):
            path = str(PurePosixPath(self.cwd_node.path) / path)
        return str(PurePosixPath(path))

    def exists(self, path: str) -> bool:
        return self._get_node(path) is not None

    def is_dir(self, path: str) -> bool:
        node = self._get_node(path)
        return node is not None and node.is_dir

    @property
    def cwd(self) -> str:
        return self.cwd_node.path

    def get_cwd_contents(self) -> list[str]:
        """Immediate children of cwd — dirs get trailing slash"""
        return sorted(
            name + ("/" if child.is_dir else "")
            for name, child in self.cwd_node.children.items()
        )

    def _extract_target(self, command: str) -> str:
        """Best-effort extraction of primary path argument"""
        parts = command.strip().split()
        if len(parts) < 2:
            return self.cwd
        for part in parts[1:]:
            if not part.startswith("-"):
                return part
        return self.cwd

    # ------------------------------------------------------------------

    def build_context(self, user_command: str) -> str:
        target     = self._extract_target(user_command)
        target_abs = self._resolve(target)
        exists     = self.exists(target_abs)
        contents   = json.dumps(self.get_cwd_contents())

        return (
            f"<environment_context>\n"
            f"[STATE]\n"
            f"User: {self.current_user}\n"
            f"CWD: {self.cwd}\n"
            f"CWD_Contents: {contents}\n\n"
            f"[PATH_CHECK_REPORT]\n"
            f"Target: {target_abs}\n"
            f"Exists: {'TRUE' if exists else 'FALSE'}\n"
            f"</environment_context>\n\n"
            f"<stdin>\n{user_command}\n</stdin>"
        )

    # ------------------------------------------------------------------

    def apply_response(self, response: dict) -> list[dict]:
        """Entry point after every parsed LLM response"""
        self._apply_state(response)
        return self._apply_fs_changes(response.get("fs_changes", []))

    def _apply_state(self, response: dict):
        new_cwd  = response.get("current_directory", self.cwd)
        new_user = response.get("current_user", self.current_user)

        node = self._get_node(new_cwd)
        if node and node.is_dir:
            self.cwd_node = node

        self.current_user = new_user

    def _apply_fs_changes(self, changes: list[dict]) -> list[dict]:
        rejected = []

        for change in changes:
            action  = change.get("action")
            path    = change.get("path")
            content = change.get("content")

            if not action or not path:
                rejected.append({**change, "reason": "missing action or path"})
                continue

            abs_path = self._resolve(path)

            if action == "create":
                parent_path = str(PurePosixPath(abs_path).parent)
                parent = self._get_node(parent_path)
                if parent is None or not parent.is_dir:
                    rejected.append({**change, "reason": f"parent {parent_path} does not exist"})
                    continue
                # Dirs reported with null content, files with string content
                if content is None:
                    result = self._mkdir(abs_path, owner=self.current_user)
                else:
                    result = self._mkfile(abs_path, content, owner=self.current_user)
                if result is None:
                    rejected.append({**change, "reason": "create failed"})

            elif action == "modify":
                node = self._get_node(abs_path)
                if node is None:
                    rejected.append({**change, "reason": f"{abs_path} does not exist"})
                    continue
                if node.is_dir:
                    rejected.append({**change, "reason": f"{abs_path} is a directory"})
                    continue
                node.content = content

            elif action == "delete":
                if not self.exists(abs_path):
                    rejected.append({**change, "reason": f"{abs_path} does not exist"})
                    continue
                self._delete(abs_path)

            else:
                rejected.append({**change, "reason": f"unknown action: {action}"})

        return rejected

    # ------------------------------------------------------------------

    def _tree_dict(self, node: VirtualNode) -> dict:
        """Recursively build a dict representation of the tree"""
        result = {"type": "dir" if node.is_dir else "file", "owner": node.owner}
        if not node.is_dir:
            result["content"] = node.content
        else:
            result["children"] = {
                name: self._tree_dict(child)
                for name, child in sorted(node.children.items())
            }
        return result

    def snapshot(self) -> dict:
        return {
            "current_user": self.current_user,
            "cwd": self.cwd,
            "tree": self._tree_dict(self.root)
        }