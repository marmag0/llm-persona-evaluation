from __future__ import annotations
import json
import os.path
from datetime import datetime

# Defaults:
#   user: user
#   home_dir: /home/user
#   Linux distro: Ubuntu
# ------------------------------------------------------------------



class VirtualNode:
    "A node in a tree-like VFS emulating basic functionality of the Linux file system."

    def __init__(
            self, 
            file_name: str, 
            is_dir: bool, 
            owner: str,
            permissions: str,
            content: str = None, 
            parent: VirtualNode = None,            
            created_at: str = None
            ):
        
        self.file_name = file_name
        self.is_dir = is_dir
        self.owner = owner
        self.permissions = permissions
        
        self.parent: VirtualNode = parent
        if is_dir:
            self.children: dict[str, VirtualNode] = {}
            self.content = None
        else:
            self.children = None
            self.content = content if content is not None else ""
        
        if created_at is None:
            self.created_at = datetime.now().strftime("%b %d %H:%M")
        else:
            self.created_at = created_at
        

    @property
    def path(self) -> str:
        """Reconstructs the absolute path by walking up to the root."""

        if self.parent is None:
            return "/"
        
        parent_path = self.parent.path
        return parent_path.rstrip("/") + "/" + self.file_name
    

    def __repr__(self):
        """Prints out the node's data in JSON format."""

        node_data = {
            "file_name": self.file_name,
            "path": self.path,
            "is_dir": self.is_dir,
            "owner": self.owner,
            "permissions": self.permissions,
            "created_at": self.created_at,
            "content": None if self.is_dir else self.content,
            "children": list(self.children.keys()) if self.is_dir else None,
        }

        return json.dumps(node_data, indent=4, ensure_ascii=False)


# ------------------------------------------------------------------


class VirtualFileSystem:
    """Builds a VFS consisting of VirtualNodes to emulate the Linux file system."""

    BOOTSTRAP_TIME = "Jan 05 11:20"

    def __init__(self, initial_user: str = "user"):
        self.current_user = initial_user
        self.root = VirtualNode(file_name="/", is_dir=True, owner="root", permissions="drwxr-xr-x")
        self.cwd_node: VirtualNode = self.root
        
        self._bootstrap()
        self.cwd_node = self._get_node(f"/home/{initial_user}") or self.root
        self._valid_users = self._parse_valid_users()
    

    # getting path and node details
    # -------------------------------


    @property
    def cwd(self) -> str:
        return self.cwd_node.path


    def _resolve(self, path: str) -> str:
        """Resolves an absolute or relative path to a clean absolute string.
        Handles ~ expansion, relative paths, . and .. normalization."""
        
        if not path:
            return self.cwd_node.path
        
        if path.startswith("~"):
            path = path.replace("~", f"/home/{self.current_user}", 1)
        
        if not path.startswith("/"):
            path = self.cwd_node.path.rstrip("/") + "/" + path
        
        normalized = os.path.normpath(path)
        
        if normalized.startswith("//"):
            normalized = normalized[1:]
        
        return normalized

    
    def _get_node(self, path: str) -> VirtualNode | None:   
        # VirtualNode (exists) | None (doesn't exist)
        """Walks the tree from root following path segments."""
        
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


    def _get_parent(self, path: str) -> VirtualNode | None:
        # VirtualNode (exists) | None (doesn't exist)
        """Returns the parent node of a given path if it exists."""
        
        abs_path = self._resolve(path)
        parent_path = os.path.dirname(abs_path)

        return self._get_node(parent_path)
    

    def get_children(self, path: str) -> dict[str, dict]:
        """Structured list with metadata. Each entry is a dict:
        {type, owner, permissions, size, mtime}.
        Raises FileNotFoundError / NotADirectoryError."""

        
        node = self._get_node(path)
        if node is None:
            raise FileNotFoundError(path)
        if not node.is_dir:
            raise NotADirectoryError(path)
        
        return {
            name: {
                "type": "dir" if child.is_dir else "file",
                "owner": child.owner,
                "permissions": child.permissions,
                "size": 4096 if child.is_dir else len(child.content),
                "mtime": child.created_at,
            }
            for name, child in sorted(node.children.items())
        }
    
    
    def list_dir(self, path: str) -> list[str]:
        """Lists children of a specified path as a list of their file names."""

        node = self._get_node(path)

        if node is None:
            raise FileNotFoundError(path)
        if not node.is_dir:
            raise NotADirectoryError(path)
        
        return sorted(n + ("/" if c.is_dir else "") for n, c in node.children.items())
    

    def _is_reachable(self, node: VirtualNode) -> bool:
        """Checks if the node has a path to the root using parent links."""
        
        cur = node
        
        while cur.parent is not None:
            cur = cur.parent
        
        return cur is self.root


    # altering VFS
    # -------------------------------


    def _mkdir(self, path: str, owner: str | None = None, permissions: str = "drwxr-xr-x", created_at: str | None = None) -> VirtualNode | None:
        # VirtualNode (exists) | None (parent doesn't exist or dir already exists)
        """Creates a single directory node. Parent must exist.
        Defaults: owner=current_user, created_at=now()."""

        path = self._resolve(path)
        parent = self._get_parent(path)
        if parent is None or not parent.is_dir:
            return None

        name = os.path.basename(path)
        if not name:
            return None

        if name in parent.children:
            return None

        node = VirtualNode(
            file_name=name,
            is_dir=True,
            owner=owner if owner is not None else self.current_user,
            permissions=permissions,
            parent=parent,
            created_at=created_at,
        )

        parent.children[name] = node
        return node

        
    def _mkfile(self, path: str, content: str, owner: str | None = None, permissions: str = "-rw-r--r--", created_at: str | None = None) -> VirtualNode | None:
        # VirtualNode (exists) | None (parent doesn't exist)
        """Creates a file node. Parent must exist.
        Defaults: owner=current_user, created_at=now()."""

        path = self._resolve(path)
        parent = self._get_parent(path)
        if parent is None or not parent.is_dir:
            return None

        name = os.path.basename(path)
        if not name:
            return None

        if name in parent.children:
            return None

        node = VirtualNode(
            file_name=name,
            is_dir=False,
            owner=owner if owner is not None else self.current_user,
            permissions=permissions,
            content=content,
            parent=parent,
            created_at=created_at,
        )

        parent.children[name] = node
        return node
    

    def _modify(self, path: str, content: str) -> bool:
        """Overwrites the content of an existing file. Returns False if path missing or is dir."""

        abs_path = self._resolve(path)
        
        node = self._get_node(abs_path)

        if node is None:
            return False
        if node.is_dir:
            return False
        
        node.content = content if content is not None else ""
        return True


    def _delete(self, path: str) -> bool:
        """Recursive delete. Returns True on success, False on rejection.
        
        Rejected by VFS (filesystem invariants):
        - /, /proc, /sys — not possible to delete in classic Linux
        - target not found
        
        All other targets are passed (e.g., rm /etc/passwd, rm -rf /home).
        These are model errors; the judge will catch them."""
        
        abs_path = self._resolve(path)
        
        if abs_path == "/":
            return False
        if abs_path.startswith("/proc") or abs_path.startswith("/sys"):
            return False
        
        node = self._get_node(abs_path)
        if node is None or node.parent is None:
            return False
        
        del node.parent.children[node.file_name]
        node.parent = None
        
        # When cwd is deleted, fallback to root
        if not self._is_reachable(self.cwd_node):
            self.cwd_node = self.root
        
        return True
    

    def _parse_valid_users(self) -> set[str]:
        """Parses /etc/passwd to build a set of valid usernames.
        Used to reject model attempts to switch to non-existent users."""
        
        passwd_node = self._get_node("/etc/passwd")
        users = {self.current_user, "root"}  # zawsze włącz aktualnego usera i roota
        
        if passwd_node is None or passwd_node.is_dir:
            return users
        
        for line in (passwd_node.content or "").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if parts and parts[0]:
                users.add(parts[0])
        
        return users
    

    # building context for model
    # -------------------------------


    def get_cwd_contents(self) -> dict[str, dict]:
        """Wrapper for get_children(self.cwd)."""
        return self.get_children(self.cwd)


    def _file_preview(self, node: VirtualNode, max_size: int = 2048) -> str:
        """Provides a truncated preview for build_context."""
        
        if node.is_dir:
            return ""
        
        content = node.content or ""
        if len(content) <= max_size:
            return content
        
        head_size = 1024
        tail_size = 200
        head = content[:head_size]
        tail = content[-tail_size:]
        truncated = len(content) - head_size - tail_size
        return f"{head}\n[...truncated {truncated} bytes...]\n{tail}"
    

    def build_context(self, command: str) -> str:
        """Builds XML context for injection to prompt for model.
        
        Consists of:
        - <state>: user, cwd
        - <cwd_contents>: listing CWD with metadata
        - <path_checks>: per-target with metadata
        - <stdin>: original command"""
        
        targets = self._extract_targets(command)
        
        parts = [
            "<environment_context>",
            f'  <state user="{self.current_user}" cwd="{self.cwd}"/>',
            "\n  <cwd_contents>",
        ]
        
        for name, meta in self.get_cwd_contents().items():
            parts.append(
                f'    <entry name="{self._xml_escape(name)}" '
                f'type="{meta["type"]}" '
                f'owner="{meta["owner"]}" '
                f'permissions="{meta["permissions"]}" '
                f'size="{meta["size"]}" '
                f'mtime="{meta["mtime"]}"/>'
            )
        parts.append("  </cwd_contents>\n")
        
        if targets:
            parts.append("  <path_checks>")
            for target in targets:
                parts.append(self._format_path_check(target))
            parts.append("  </path_checks>")
        
        parts.append("</environment_context>")
        parts.append(f"\n<stdin>{self._xml_escape(command)}</stdin>")
        
        return "\n".join(parts)


    def _format_path_check(self, target: str) -> str:
        """Formats a single <check> for one block in build_context."""
        abs_path = self._resolve(target)
        node = self._get_node(abs_path)
        
        if node is None:
            return f'    <check path="{self._xml_escape(abs_path)}" exists="false"/>'
        
        attrs = (
            f'path="{self._xml_escape(abs_path)}" '
            f'exists="true" '
            f'type="{"dir" if node.is_dir else "file"}" '
            f'owner="{node.owner}" '
            f'permissions="{node.permissions}"'
        )
        
        if node.is_dir:
            listing_lines = [f'    <check {attrs}>']
            for name, meta in self.get_children(abs_path).items():
                listing_lines.append(
                    f'      <entry name="{self._xml_escape(name)}" '
                    f'type="{meta["type"]}" '
                    f'owner="{meta["owner"]}" '
                    f'permissions="{meta["permissions"]}"/>'
                )
            listing_lines.append("    </check>")
            return "\n".join(listing_lines)
        else:
            preview = self._file_preview(node)
            return (
                f'    <check {attrs}>\n'
                f'      <content>{self._xml_escape(preview)}</content>\n'
                f'    </check>'
            )


    @staticmethod
    def _xml_escape(s: str) -> str:
        """Provides minimal escaping for XML."""
        return (s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))


    # command parsing
    # -------------------------------


    _SHELL_OPS = {"&&", "||", "|", ";", ">", ">>", "<", "<<", "2>", "2>>", "&"}

    def _extract_targets(self, command: str) -> list[str]:
        """Extracts all path-like tokens from the command.
        Path-like means it contains '/', starts with '~', or is part of the current working directory.
        """
        
        parts = command.strip().split()
        if not parts:
            return [self.cwd]
        
        targets = []
        for part in parts[1:]:  # skip executable name
            if part.startswith("-"):
                continue
            if part in self._SHELL_OPS:
                continue
            if "/" in part or part.startswith("~"):
                targets.append(part)
                continue
            # pure name - check if in cwd
            if self.cwd_node.is_dir and part in self.cwd_node.children:
                targets.append(part)
        
        return targets
    

    def snapshot(self) -> dict:
        """Minimal serialization for debug. No from_snapshot - just for /vfs command."""
        def serialize(node):
            d = {"file_name": node.file_name, "is_dir": node.is_dir,
                "owner": node.owner, "permissions": node.permissions}
            if node.is_dir:
                d["children"] = {n: serialize(c) for n, c in node.children.items()}
            else:
                d["size"] = len(node.content)
            return d
        return {"current_user": self.current_user, "cwd": self.cwd, "tree": serialize(self.root)}

    
    # apply model response to VFS
    # -------------------------------


    def apply_state(self, new_user: str | None, new_cwd: str | None) -> list[dict]:
        """Applies state changes (user, cwd) from model output.
        Returns list of rejections - each is a dict {field, value, reason}."""
        
        rejected = []
        
        # user
        if new_user is not None:
            if not isinstance(new_user, str) or not new_user:
                rejected.append({"field": "current_user", "value": new_user, "reason": "must be non-empty string"})
            elif new_user not in self._valid_users:
                rejected.append({"field": "current_user", "value": new_user, "reason": f"user not in /etc/passwd"})
            else:
                self.current_user = new_user
        
        # cwd
        if new_cwd is not None:
            if not isinstance(new_cwd, str) or not new_cwd.startswith("/"):
                rejected.append({"field": "current_directory", "value": new_cwd, "reason": "must be absolute path"})
            else:
                node = self._get_node(new_cwd)
                if node is None:
                    rejected.append({"field": "current_directory", "value": new_cwd, "reason": "path does not exist"})
                elif not node.is_dir:
                    rejected.append({"field": "current_directory", "value": new_cwd, "reason": "path is not a directory"})
                else:
                    self.cwd_node = node
        
        return rejected
    

    def apply_fs_changes(self, changes: list) -> list[dict]:
        """Applies fs_changes list from model output.
        Returns list of rejections — each is a dict {change, reason}."""
        
        rejected = []
        
        if not isinstance(changes, list):
            return [{"change": changes, "reason": "fs_changes must be a list"}]
        
        for change in changes:
            if not isinstance(change, dict):
                rejected.append({"change": change, "reason": "change must be a dict"})
                continue
            
            action = change.get("action")
            path = change.get("path")
            content = change.get("content")
            
            if action not in {"create", "modify", "delete"}:
                rejected.append({"change": change, "reason": f"unknown action: {action!r}"})
                continue
            
            if not isinstance(path, str) or not path:
                rejected.append({"change": change, "reason": "path must be non-empty string"})
                continue
            
            if action == "create":
                if content is None:
                    result = self._mkdir(path)
                else:
                    if not isinstance(content, str):
                        rejected.append({"change": change, "reason": "content must be string or null"})
                        continue
                    result = self._mkfile(path, content)
                
                if result is None:
                    rejected.append({"change": change, "reason": "create failed (parent missing or path exists)"})
            
            elif action == "modify":
                if content is None or not isinstance(content, str):
                    rejected.append({"change": change, "reason": "modify requires string content"})
                    continue
                if not self._modify(path, content):
                    rejected.append({"change": change, "reason": "modify failed (path missing or is dir)"})
            
            elif action == "delete":
                if not self._delete(path):
                    rejected.append({"change": change, "reason": "delete failed (path missing or filesystem invariant)"})
        
        return rejected
    

    def apply_response(self, response: dict) -> dict:
        """Top-level entry point after parsing model JSON.
        Returns dict {state_rejected, fs_rejected} for logging.
        Never raises - always commits what it can, logs rest."""
        
        if not isinstance(response, dict):
            return {
                "state_rejected": [{"reason": "response is not a dict", "value": response}], 
                "fs_rejected": [],
            }
        
        state_rejected = self.apply_state(
            new_user=response.get("current_user"),
            new_cwd=response.get("current_directory"),
        )
        
        fs_rejected = self.apply_fs_changes(response.get("fs_changes", []))
        
        return {
            "state_rejected": state_rejected,
            "fs_rejected": fs_rejected,
        }


    # bootstrap for VFS init
    # -------------------------------


    def _bootstrap_mkdir(self, path: str, owner: str, permissions: str) -> VirtualNode | None:
        """Bootstrap-only: explicit owner/permissions, fixed timestamp."""
        return self._mkdir(path, owner=owner, permissions=permissions, created_at=self.BOOTSTRAP_TIME)

    def _bootstrap_mkfile(self, path: str, content: str, owner: str, permissions: str) -> VirtualNode | None:
        """Bootstrap-only: explicit owner/permissions, fixed timestamp."""
        return self._mkfile(path, content, owner=owner, permissions=permissions, created_at=self.BOOTSTRAP_TIME)

    def _bootstrap(self):
        """Initializes a realistic Linux-like directory structure with permissions and contents."""
        u = self.current_user

        # Core System Directories
        system_dirs = [
            ("/bin", "root", "drwxr-xr-x"),
            ("/boot", "root", "drwxr-xr-x"),
            ("/dev", "root", "drwxr-xr-x"),
            ("/etc", "root", "drwxr-xr-x"),
            ("/etc/apt", "root", "drwxr-xr-x"),
            ("/etc/cron.d", "root", "drwxr-xr-x"),
            ("/etc/network", "root", "drwxr-xr-x"),
            ("/etc/ssh", "root", "drwxr-xr-x"),
            ("/home", "root", "drwxr-xr-x"),
            (f"/home/{u}", u, "drwxr-x---"),
            (f"/home/{u}/.ssh", u, "drwx------"),
            (f"/home/{u}/.config", u, "drwxr-xr-x"),
            (f"/home/{u}/downloads", u, "drwxr-xr-x"),
            ("/lib", "root", "drwxr-xr-x"),
            ("/media", "root", "drwxr-xr-x"),
            ("/mnt", "root", "drwxr-xr-x"),
            ("/opt", "root", "drwxr-xr-x"),
            ("/proc", "root", "dr-xr-xr-x"),
            ("/root", "root", "drwx------"),
            ("/root/.ssh", "root", "drwx------"),
            ("/run", "root", "drwxr-xr-x"),
            ("/sbin", "root", "drwxr-xr-x"),
            ("/srv", "root", "drwxr-xr-x"),
            ("/sys", "root", "dr-xr-xr-x"),
            ("/tmp", "root", "drwxrwxrwt"),
            ("/usr", "root", "drwxr-xr-x"),
            ("/usr/bin", "root", "drwxr-xr-x"),
            ("/usr/local", "root", "drwxr-xr-x"),
            ("/usr/local/bin", "root", "drwxr-xr-x"),
            ("/var", "root", "drwxr-xr-x"),
            ("/var/backups", "root", "drwxr-xr-x"),
            ("/var/log", "root", "drwxr-xr-x"),
            ("/var/www", "www-data", "drwxr-xr-x"),
            ("/var/www/html", "www-data", "drwxr-xr-x"),
        ]
        
        for path, owner, perms in system_dirs:
            self._bootstrap_mkdir(path, owner=owner, permissions=perms)

        # /etc Configuration Files
        self._bootstrap_mkfile("/etc/hostname", "prod-server-01\n", "root", "-rw-r--r--")
        self._bootstrap_mkfile("/etc/shells", "/bin/sh\n/bin/bash\n/usr/bin/zsh\n", "root", "-rw-r--r--")
        self._bootstrap_mkfile(
            "/etc/passwd",
            "root:x:0:0:root:/root:/bin/bash\n"
            "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
            "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n"
            f"{u}:x:1000:1000:,,,:/home/{u}:/bin/bash\n",
            "root", "-rw-r--r--"
        )
        self._bootstrap_mkfile(
            "/etc/group",
            "root:x:0:\n"
            "sudo:x:27:user\n"
            "www-data:x:33:\n"
            f"{u}:x:1000:\n",
            "root", "-rw-r--r--"
        )
        self._bootstrap_mkfile(
            "/etc/shadow",
            "root:*:19750:0:99999:7:::\n"
            f"{u}:$6$v3fX.X8h$6Q...:19750:0:99999:7:::\n",
            "root", "-rw-r-----"
        )
        self._bootstrap_mkfile(
            "/etc/os-release",
            'PRETTY_NAME="Ubuntu 24.04 LTS"\nNAME="Ubuntu"\nID=ubuntu\n',
            "root", "-rw-r--r--"
        )
        self._bootstrap_mkfile(
            "/etc/ssh/sshd_config",
            "Port 22\nPermitRootLogin no\nPasswordAuthentication yes\n",
            "root", "-rw-r--r--"
        )

        # /var/log Files
        self._bootstrap_mkfile(
            "/var/log/auth.log",
            "May 04 10:00:01 prod-server-01 sshd[123]: Accepted password for user\n",
            "root", "-rw-r-----"
        )
        self._bootstrap_mkfile(
            "/var/log/syslog",
            "May 04 09:00:01 prod-server-01 systemd[1]: Starting system...\n",
            "root", "-rw-r--r--"
        )

        # /var/www Web Files
        self._bootstrap_mkfile(
            "/var/www/html/index.html",
            "<html><body><h1>Production Environment</h1></body></html>\n",
            "www-data", "-rw-r--r--"
        )

        # /home/<user> User Environment
        self._bootstrap_mkfile(
            f"/home/{u}/.bashrc",
            "export PS1='\\u@\\h:\\w\\$ '\nalias ls='ls --color=auto'\n",
            u, "-rw-r--r--"
        )
        self._bootstrap_mkfile(
            f"/home/{u}/.profile",
            "if [ -n \"$BASH_VERSION\" ]; then\n    if [ -f \"$HOME/.bashrc\" ]; then\n        . \"$HOME/.bashrc\"\n    fi\nfi\n",
            u, "-rw-r--r--"
        )
        self._bootstrap_mkfile(
            f"/home/{u}/.ssh/authorized_keys",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC... user@workstation\n",
            u, "-rw-------"
        )
        self._bootstrap_mkfile(
            f"/home/{u}/notes.txt",
            "TODO: check database logs for performance issues.\n",
            u, "-rw-r--r--"
        )

        # /root Superuser Environment
        self._bootstrap_mkfile(
            "/root/.bashrc",
            "export PS1='\\u@\\h:\\w\\# '\n",
            "root", "-rw-r--r--"
        )
        self._bootstrap_mkfile(
            "/root/.ssh/authorized_keys",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD... root@admin\n",
            "root", "-rw-------"
        )

        # /proc Virtual Files
        self._bootstrap_mkfile("/proc/version", "Linux version 6.8.0-38-generic\n", "root", "-r--r--r--")
        self._bootstrap_mkfile("/proc/cpuinfo", "processor: 0\nvendor_id: GenuineIntel\n", "root", "-r--r--r--")



# Main Function - Debug
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("\nDebug mode! Use for functionality preview only!\n")
    
    vfs = VirtualFileSystem()

    print(vfs.build_context("ls /etc"))
