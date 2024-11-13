import json
import re
import struct
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote

import httpx
from aiofiles import open
from tenacity import retry, stop_after_attempt, wait_fixed


@dataclass
@dataclass
class HitomiDetail:
    title: str
    url: str
    language: str
    type: str
    series: list[str]
    tags: list[str]


DataType = dict[str, Any]


def cache_manager(func):
    cache: list[tuple[Any, Any]] = []

    async def wrapper(self, *args, **kwargs):
        for arg, value in cache:
            if arg == args:
                return value

        res = await func(self, *args, **kwargs)
        cache.append((args, res))
        return res

    return wrapper


class Hitomi:
    def __init__(self, client: httpx.AsyncClient, headers: dict):
        self.client = client
        self.headers = headers

    async def request(self, url: str, headers: dict = {}):
        response = await self.client.get(url, headers=headers)
        assert response.status_code >= 200 and response.status_code < 300
        return response

    async def get_data(self, input: str) -> list[str]:
        url = input.replace("hitomi.la", "ltn.hitomi.la", 1).replace(
            ".html", ".nozomi", 1
        )
        inf = 2**31 - 1
        response = await self.request(
            url, {"Referer": "https://hitomi.la/", "Range": f"bytes=0-{inf}"}
        )
        total = len(response.content) // 4
        res = [
            str(struct.unpack(">i", response.content[i * 4 : (i + 1) * 4])[0])
            for i in range(total)
        ]
        return res

    async def gg(self) -> tuple[str, list[str], str, str]:
        response = await self.request("https://ltn.hitomi.la/gg.js")
        b = re.search(r"b: '([0-9]+)\/'", response.content.decode()).group(1)  # type: ignore
        m = re.findall(r"case ([0-9]+):", response.content.decode())  # type: ignore
        o = re.search(r"var o = ([0-9]+);", response.content.decode()).group(1)  # type: ignore
        o2 = re.search(r"o = ([0-9]+); break;", response.content.decode()).group(1)  # type: ignore
        return b, m, o, o2

    def s(self, h: str) -> str:
        m = re.search(r"(..)(.)$", h)
        return str(int(m.group(2) + m.group(1), 16))  # type: ignore

    def subdomain_from_url(
        self, hash: str, ggm: list[str], ggb: str, ggo: str, ggo2: str
    ) -> str:
        retval = "a"
        b = 16

        r = re.compile(r"[0-9a-f]{61}([0-9a-f]{2})([0-9a-f])")
        m = r.search(hash)
        if not m:
            return "a"

        g = int(m.group(2) + m.group(1), b)
        if not isinstance(g, int):
            return "a"

        a = int(ggo2) if str(g) in ggm else int(ggo)

        retval = chr(97 + a) + retval
        return f"https://{retval}.hitomi.la/webp/{ggb}/{self.s(hash)}/{hash}.webp"

    async def galleryblock(self, id: str) -> tuple[dict[str, Any], list[str]]:
        detail = await self.request(f"https://ltn.hitomi.la/galleries/{id}.js")
        data = json.loads(detail.content.decode().replace("var galleryinfo = ", ""))
        b, m, o, o2 = await self.gg()
        urls = [
            self.subdomain_from_url(files["hash"], m, b, o, o2)
            for files in data["files"]
        ]
        return data, urls

    def get_details(self, content: str) -> tuple[str, str]:
        re_title = '<h1{any}><a href="{url}"{any}>{name}</a></h1>'.format(
            any=r"[\s\S]*?",
            url=r"(?P<url>[\s\S]*?)",
            name=r"(?P<name>[\s\S]*?)",
        )
        url = re.compile(re_title).search(content).group("url")  # type: ignore
        id = re.search(r"([0-9]+)(?:\.html)?$", url).group(1)  # type: ignore
        return id, url


class HitomiDownloader:
    def __init__(
        self,
        client: httpx.AsyncClient,
        userAgent: str,
    ):
        self.hitomi = Hitomi(client, {"User-Agent": userAgent})

    @classmethod
    async def factrory(
        cls,
        client: httpx.AsyncClient,
        ua: Optional[str] = None,
    ):
        new_ua = ua or await cls.ua(client)
        return cls(client, new_ua)

    @staticmethod
    async def ua(client: httpx.AsyncClient) -> str:
        url = "https://raw.githubusercontent.com/fa0311/latest-user-agent/main/output.json"
        response = await client.get(url)
        return response.json()["chrome"]

    @staticmethod
    async def input(path: str) -> list[str]:
        async with open(path, encoding="utf-8") as f:
            data = await f.read()

        artist = re.findall(r"https://hitomi.la/artist/(.+).html", data)
        return artist

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        return re.sub(r"[\\/:*?\"<>|#]", "", filename).rstrip(" .")

    def get_title(self, data: DataType) -> str:
        title = data.get("japanese_title") or data["title"]
        return self.sanitize_filename(title)

    def get_tags(self, data: DataType) -> list[str]:
        return [tag["tag"] for tag in (data.get("tags") or [])]

    def get_series(self, data: DataType) -> list[str]:
        return [series["parody"] for series in (data.get("series") or [])]

    def get_characters(self, data: DataType) -> list[str]:
        return [character["character"] for character in (data.get("characters") or [])]

    def get_referer(self, data: DataType) -> str:
        return f"https://hitomi.la/{quote(data['galleryurl'])}"

    async def get_data(self, input: str):
        return await self.hitomi.get_data(input)

    async def galleryblock(self, id: str):
        return await self.hitomi.galleryblock(id)

    @retry(stop=stop_after_attempt(9999999), wait=wait_fixed(3))
    async def save(self, url: str, data: DataType):
        res = await self.hitomi.request(url, {"Referer": self.get_referer(data)})
        return res.content
