import xml.etree.ElementTree as ET
from typing import Optional

import httpx


class NextCloud:
    def __init__(
        self, client: httpx.AsyncClient, username: str, password: str, url: str
    ):
        self.client = client
        self.username = username
        self.password = password
        self.url = url
        self.current = ""

    def cd(self, path: str):
        self.current = path + "/"

    async def mkdir(self, path: str) -> Optional[str]:
        response = await self.client.request(
            "MKCOL",
            f"{self.url}/remote.php/dav/files/{self.username}/{self.current}{path}",
            auth=(self.username, self.password),
        )

        if response.status_code == 201:
            file_id = response.headers["oc-fileid"]
            return file_id
        return None

    async def request(self, method: str, path: str, tags: list):
        root = ET.Element(
            "d:propfind",
            {
                "xmlns:d": "DAV:",
                "xmlns:oc": "http://owncloud.org/ns",
                "xmlns:nc": "http://nextcloud.org/ns",
            },
        )
        prop = ET.SubElement(root, "d:prop")
        for tag in tags:
            ET.SubElement(prop, tag)

        tag_namespace = {
            "d": "DAV:",
            "oc": "http://owncloud.org/ns",
            "nc": "http://nextcloud.org/ns",
        }
        response = await self.client.request(
            method,
            path,
            content=ET.tostring(root),
            auth=(self.username, self.password),
        )
        assert response.status_code == 207
        root = ET.fromstring(response.content)
        tuples = []
        for response in root.findall(".//d:response", tag_namespace):
            status = response.find(".//d:status", tag_namespace)
            if status is not None and status.text == "HTTP/1.1 200 OK":
                elem = []
                for tag in tags:
                    tag_elem = response.find(f".//{tag}", tag_namespace)
                    if tag_elem is None:
                        raise Exception(f"Tag {tag} not found")
                    elif tag_elem.text is None:
                        tag_elems = response.findall(f".//{tag}/*", tag_namespace)
                        elem.append([tag_elem.text for tag_elem in tag_elems])
                    else:
                        elem.append(tag_elem.text)
                tuples.append(tuple(elem))
        return tuples

    async def path_list(self, path) -> list[tuple]:
        res = await self.request(
            "PROPFIND",
            f"{self.url}/remote.php/dav/files/{self.username}/{self.current}{path}",
            [
                "d:getlastmodified",
                "d:getcontenttype",
                "oc:fileid",
                "d:href",
                "d:displayname",
                "nc:system-tags",
            ],
        )
        return res

    async def recursive_path_list(self, path: str) -> list[tuple]:
        children: list[tuple] = []
        images = await self.path_list(path)

        for timestamp, content_type, id, image, displayname, tags in images[1:]:
            if image.endswith("/"):
                children.extend(await self.recursive_path_list(f"{path}/{displayname}"))

        return [*images[1:], *children]

    async def download(self, id):
        response = await self.client.request(
            "GET",
            f"{self.url}/core/preview",
            params={"fileId": id, "a": "true", "x": 3840, "y": 2160},
            auth=(self.username, self.password),
        )
        return response.content

    async def upload(self, path: str, content: bytes):
        response = await self.client.request(
            "PUT",
            f"{self.url}/remote.php/dav/files/{self.username}/{self.current}{path}",
            content=content,
            headers={"Content-Type": "image/webp"},
            auth=(self.username, self.password),
        )
        assert response.status_code == 201
        file_id = response.headers["oc-fileid"]
        return file_id

    async def get_tags(self):
        res = await self.request(
            "PROPFIND",
            f"{self.url}/remote.php/dav/systemtags/",
            [
                "oc:id",
                "oc:display-name",
            ],
        )
        return res

    async def create_tag(
        self,
        name,
        user_visible=True,
        user_assignable=True,
        can_assign=True,
    ):
        await self.client.request(
            "POST",
            self.url + "/remote.php/dav/systemtags/",
            json={
                "userVisible": user_visible,
                "userAssignable": user_assignable,
                "canAssign": can_assign,
                "name": name,
            },
            auth=(self.username, self.password),
        )

    async def assign_tag(self, file_id, tag_id):
        response = await self.client.request(
            "PUT",
            self.url + f"/remote.php/dav/systemtags-relations/files/{file_id}/{tag_id}",
            auth=(self.username, self.password),
        )
        assert response.status_code == 201
        return response.text

    async def unassign_tag(self, file_id, tag_id):
        response = await self.client.request(
            "DELETE",
            self.url + f"/remote.php/dav/systemtags-relations/files/{file_id}/{tag_id}",
            auth=(self.username, self.password),
        )
        assert response.status_code == 204
        return response.text
