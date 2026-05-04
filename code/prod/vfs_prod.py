from __future__ import annotations
import json
from pathlib import PurePosixPath
from datetime import datetime

# defaults:
#   user: user
#   home_dir: /home/user
#   linux distro: Ubuntu
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
            created_at: datetime = None
            ):
        
        self.file_name = file_name
        self.is_dir = is_dir
        self.owner = owner
        
        self.parent: VirtualNode = parent
        if is_dir:
            self.children: dict[str, VirtualNode] = {}
            self.content = None
        else:
            self.children = None
            self.content = content
        
        if created_at is None:
            self.created_at = datetime.now().strftime("%b %d %H:%M")
        else:
            self.created_at = created_at
        

    @property
    def path(self) -> str:
        """Reconstructs the absolute path by walking up to the root."""

        if self.parent == None:
            absolute_path = "/"
        else:
            absolute_path = self.parent.path
        
        return absolute_path.rstrip("/") + self.file_name
    

    def __repr__(self):
        "Prints out node's data in JSON format"

        node_data = {
            "file_name": self.file_name,
            "path": self.path,
            "is_dir": self.is_dir,
            "owner": self.owner,
            "permissions": self.permissions,
            "created": self.created,
            "content": None if self.is_dir else self.content,
            "children": list(self.children.keys()) if self.is_dir else None,
        }

        return json.dumps(node_data, indent=4, ensure_ascii=False)


# ------------------------------------------------------------------


class VirtualFileSystem:
    """Building VFS consisting of VirtualNodes to emulate Linux File System"""

    def __init__(self, initial_user: str = "user"):
        self.current_user = initial_user
        self.root = VirtualNode(file_name="/", is_dir=True, owner="root", permissions="drwxr-xr-x")
        self.cwd_nod: VirtualNode = self.root
        
        self._bootstrap()
        # TODO _get_node
        self.cwd_node = self._get_node(f"/home/{initial_user}") or self.root
    

    pass


    def _bootstrap(self):
        pass










    
