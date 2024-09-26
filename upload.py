import asyncio
import io
from typing import Optional

import httpx
from PIL import Image
from retry import retry
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
        ua: Optional[str] = None,
    ):
        new_ua = ua or await cls.ua(client)
        return cls(
            client,
            new_ua,
            asyncio.Semaphore(semaphore),
            nextcloud,
            await TagManager.facory(nextcloud),
        )

    @retry(tries=30, delay=1)
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
                    await self.save(url, f"{output}/{title}_{id}/{i:04}.png", data)

                task = [self.set_tag(field_id, tag) for tag in tags]
                await asyncio.gather(*task)

            else:
                print(f"fiald to create {output}/{title}_{id}")

    @retry(tries=30, delay=1)
    async def save(self, url: str, output: str, data: dict):
        response = await self.hitomi.request(url, {"Referer": self.get_referer(data)})
        png = io.BytesIO()
        content = Image.open(io.BytesIO(response.content))
        content.save(png, "PNG")

        await self.nextcloud.upload(output, png.getvalue())

    async def set_tag(self, file_id: str, tag: str):
        tag_id = await self.tag.get_tag_id(tag)
        await self.nextcloud.assign_tag(file_id, tag_id)


async def main():
    client = httpx.AsyncClient(timeout=None)
    env = Settings()
    nextcloud = NextCloud(client, env.username, env.password, env.url)
    nextcloud.cd(env.path)
    downloader = await HitomiDownloaderUpload.factrory(client, nextcloud, semaphore=1)
    artist = await downloader.input("input.txt")
    for file in artist:
        artist, lang = file.rsplit("-", 1)
        sanitaized = downloader.sanitize_filename(artist)
        await nextcloud.mkdir(sanitaized)
        await downloader.download_all(
            f"https://hitomi.la/artist/{file}.html",
            output=sanitaized,
        )


if __name__ == "__main__":
    asyncio.run(main())
