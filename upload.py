import asyncio
import io
import re

import httpx
from aiofiles import open
from PIL import Image
from tqdm import tqdm

from src.config import Settings
from src.hitomi import HitomiDownloader
from src.manager import TagManager
from src.nextcloud import NextCloud


class HitomiDownloaderUpload(HitomiDownloader):
    def __init__(
        self,
        client: httpx.AsyncClient,
        userAgent: str,
        semaphore: asyncio.Semaphore,
        nextcloud: NextCloud,
        tag: TagManager,
    ):
        super().__init__(client, userAgent, semaphore)
        self.nextcloud = nextcloud
        self.tag = tag

    @classmethod
    async def factrory(
        cls,
        client: httpx.AsyncClient,
        nextcloud: NextCloud,
        semaphore: int = 10,
    ):
        return cls(
            client,
            await cls.ua(client),
            asyncio.Semaphore(semaphore),
            nextcloud,
            await TagManager.facory(nextcloud),
        )

    async def download(self, id: str, output: str):
        async with self.semaphore:
            data, urls = await self.hitomi.galleryblock(id)
            title = self.get_title(data)
            tags = [
                *self.get_tags(data),
                *self.get_series(data),
                *self.get_characters(data),
            ]
            field_id = await self.nextcloud.mkdir(f"{output}/{title}_{id}")
            if field_id:
                for i, url in enumerate(tqdm(urls, desc=title, leave=False)):
                    response = await self.hitomi.request(
                        url, {"Referer": self.get_referer(data)}
                    )
                    o = f"{output}/{title}_{id}/{i:04}.png"
                    asyncio.ensure_future(self.upload(o, response.content))
                asyncio.ensure_future(self.set_tags(field_id, tags))

            else:
                print(f"{title} already exists")

    async def upload(self, output: str, raw: bytes):
        png = io.BytesIO()
        content = Image.open(io.BytesIO(raw))
        content.save(png, "PNG")

        await self.nextcloud.upload(output, png.getvalue())

    async def set_tags(self, file_id: str, tags: list[str]):
        task = [self.set_tag(file_id, tag) for tag in tags]
        await asyncio.gather(*task)

    async def set_tag(self, file_id: str, tag: str):
        tag_id = await self.tag.get_tag_id(tag)
        await self.nextcloud.assign_tag(file_id, tag_id)


async def main():
    client = httpx.AsyncClient()
    env = Settings()
    nextcloud = NextCloud(client, env.username, env.password, env.url)
    nextcloud.cd(env.path)
    downloader = await HitomiDownloaderUpload.factrory(client, nextcloud, semaphore=1)

    async with open("input.txt", encoding="utf-8") as f:
        data = await f.read()

    artist = re.search(r"https://hitomi.la/artist/(.+).html", data)

    file = artist.group(1)  # type: ignore

    artist, lang = file.rsplit("-", 1)
    await nextcloud.mkdir(artist)
    await downloader.download_all(
        f"https://hitomi.la/artist/{file}.html",
        output=artist,
    )


if __name__ == "__main__":
    asyncio.run(main())
