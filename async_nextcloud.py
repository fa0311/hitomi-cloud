import asyncio

import httpx
from tqdm import tqdm

from src.config import Settings
from src.hitomi import HitomiDownloader
from src.manager import TagManager
from src.nextcloud import NextCloud


def print(*args, **kwargs):
    tqdm.write(" ".join(map(str, args)), **kwargs)


async def download_all_async(
    downloader: HitomiDownloader,
    tag: TagManager,
    nextcloud: NextCloud,
    output: str,
    desc: str,
    field_id: str,
    data: dict,
    urls: list[str],
    semaphore1: asyncio.Semaphore = asyncio.Semaphore(10),
    semaphore2: asyncio.Semaphore = asyncio.Semaphore(3),
) -> None:
    async with semaphore1:
        for i, url in enumerate(tqdm(urls, leave=False, desc=desc)):
            async with semaphore2:
                bin = await downloader.save(url, data)
            await nextcloud.upload(f"{output}/{i:04}.webp", bin)

        tags = [
            *downloader.get_tags(data),
            *downloader.get_series(data),
            *downloader.get_characters(data),
        ]
        for tag_name in tags:
            tag_id = await tag.get_tag_id(tag_name)
            await nextcloud.assign_tag(field_id, tag_id)


async def get_data(
    downloader: HitomiDownloader,
    url: str,
    semaphore: asyncio.Semaphore = asyncio.Semaphore(10),
):
    async with semaphore:
        return await downloader.get_data(url)


async def get_galleryblock(
    downloader: HitomiDownloader,
    id: str,
    semaphore: asyncio.Semaphore = asyncio.Semaphore(10),
):
    async with semaphore:
        return id, *(await downloader.galleryblock(id))


async def main():
    client = httpx.AsyncClient()
    downloader = await HitomiDownloader.factrory(client)
    env = Settings()
    nextcloud = NextCloud(client, env.username, env.password, env.url)
    nextcloud.cd(env.path)
    tag = await TagManager.facory(nextcloud)
    artist = await downloader.input("input.txt")

    artist_url = [f"https://hitomi.la/artist/{file}.html" for file in artist]
    ids_list = await asyncio.gather(*[get_data(downloader, url) for url in artist_url])

    manga = []

    for file, ids in zip(artist, ids_list):
        artist, lang = file.rsplit("-", 1) if "-" in file else (file, "all")
        artist_filename = downloader.sanitize_filename(artist)

        future = [get_galleryblock(downloader, id) for id in ids]
        data_list = await asyncio.gather(*future)
        for id, data, urls in data_list:
            title = downloader.get_title(data)
            output = f"{artist_filename}/{title}_{id}"
            await nextcloud.mkdir(artist_filename)
            field_id = await nextcloud.mkdir(output)
            if field_id is None:
                print(f"Skip {output}")
            else:
                print(f"Download {output}")
                manga.append((output, title, field_id, data, urls))

    tasks = [download_all_async(downloader, tag, nextcloud, *args) for args in manga]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
