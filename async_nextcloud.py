import asyncio
import urllib.parse

import httpx
from tenacity import retry, stop_after_attempt, wait_random
from tqdm import tqdm

from src.config import Settings
from src.hitomi import HitomiArtistQueue, HitomiDownloader
from src.manager import TagManager
from src.nextcloud import NextCloud

TEMP_PREFIX = "temp-"


def print(*args, **kwargs):
    tqdm.write(" ".join(map(str, args)), **kwargs)


@retry(stop=stop_after_attempt(10), wait=wait_random(0, 10))
async def move(nextcloud, output2, output):
    await nextcloud.move(output2, output)


async def download_all_async(
    downloader: HitomiDownloader,
    tag: TagManager,
    nextcloud: NextCloud,
    output: str,
    output2: str,
    desc: str,
    data: dict,
    urls: list[str],
    end_tag: str,
    semaphore: asyncio.Semaphore = asyncio.Semaphore(10),
) -> None:
    async with semaphore:
        filename, field_id = await mkdir_retry(nextcloud, output2)
        for i, url in enumerate(tqdm(urls, leave=False, desc=desc)):
            bin = await downloader.save(url, data)
            await nextcloud.upload(f"{filename}/{i:04}.webp", bin)
        tags = [
            *downloader.get_tags(data),
            *downloader.get_series(data),
            *downloader.get_characters(data),
        ]
        for tag_name in tqdm(tags, leave=False, desc="Assign tags"):
            tag_id = await tag.get_tag_id(tag_name)
            await nextcloud.assign_tag(field_id, tag_id)

        await nextcloud.assign_tag(field_id, end_tag)
        await asyncio.sleep(1)
        await move(nextcloud, filename, output)

async def mkdir_retry(nextcloud, path)-> tuple[str, str]:
    for attempt in range(3):
        field_id = await nextcloud.mkdir(f"{path}-{attempt}")
        if field_id:
            return (f"{path}-{attempt}", field_id)
    raise Exception(f"Failed to create directory {path} after 3 attempts")


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
        return await downloader.galleryblock(id)


async def main():
    client = httpx.AsyncClient(timeout=None)
    downloader = await HitomiDownloader.factrory(client)
    env = Settings()
    nextcloud = NextCloud(client, env.username, env.password, env.url)
    nextcloud.cd(env.path)
    tag = await TagManager.facory(nextcloud)
    artist_queue = await HitomiArtistQueue.input_from_cache("input.txt")

    artist_url = [f"https://hitomi.la/artist/{file}.html" for file in artist_queue]
    ids_list = await asyncio.gather(*[get_data(downloader, url) for url in artist_url])
    invisible_tag_id = await tag.get_tag_id(env.invisible_tags, hidden=True)

    manga = []
    for file, ids in tqdm(zip(artist_queue, ids_list), total=len(artist_queue), leave=True):
        artist, lang = file.rsplit("-", 1) if "-" in file else (file, "all")
        artist_filename = downloader.sanitize_filename(urllib.parse.unquote(artist))

        await nextcloud.mkdir(artist_filename)
        images = await nextcloud.path_list(artist_filename)
        displaynames = [displayname for _, _, _, _, displayname, _ in images[1:]]
        for displayname in displaynames:
            if displayname.startswith(TEMP_PREFIX):
                print(f"Delete {displayname}")
                await nextcloud.delete(f"{artist_filename}/{displayname}")

        future = [get_galleryblock(downloader, id) for id in ids]
        data_list = await asyncio.gather(*future)
        for id, (data, urls) in zip(ids, data_list):
            title = downloader.sanitize_filename(downloader.get_title(data))
            artist_filename = downloader.sanitize_filename(urllib.parse.unquote(artist))
            output = f"{artist_filename}/{int(id):09}_{title}"
            output2 = f"{artist_filename}/{TEMP_PREFIX}{int(id):09}"
            if f"{int(id):09}" not in [x.split("_")[0] for x in displaynames]:
                print(f"Download {output}")
                manga.append((output, output2, title, data, urls, invisible_tag_id))
        await artist_queue.pop()

    tasks = [download_all_async(downloader, tag, nextcloud, *args) for args in manga]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
