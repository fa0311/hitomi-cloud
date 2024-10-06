import asyncio

import httpx
from aiofiles import open, os
from tqdm import tqdm

from src.hitomi import HitomiDownloader


def print(*args, **kwargs):
    tqdm.write(" ".join(map(str, args)), **kwargs)


async def download_all_async(
    downloader: HitomiDownloader,
    output: str,
    desc: str,
    data: dict,
    urls: list[str],
    semaphore: asyncio.Semaphore = asyncio.Semaphore(10),
) -> None:
    async with semaphore:
        for i, url in enumerate(tqdm(urls, leave=False, desc=desc)):
            bin = await downloader.save(url, data)
            async with open(f"{output}/{i:04}.webp", "wb") as f:
                await f.write(bin)


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
            output = f"output/{artist_filename}/{title}_{id}"
            await os.makedirs(output, exist_ok=True)
            manga.append((output, title, data, urls))

    tasks = [download_all_async(downloader, *args) for args in manga]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
