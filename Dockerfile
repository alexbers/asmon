FROM ubuntu:22.04

RUN useradd asmon -u 40000 -M
RUN mkdir /home/asmon

RUN apt-get update && apt-get install --no-install-recommends -y python3 tzdata python3-aiohttp python3-httpx ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /home/asmon/
CMD ["./start.sh"]
