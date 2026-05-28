async def byte_stream_producer(
    stream,
    queue
):

    while True:

        print(
            "[PRODUCER] reading chunk..."
        )
        chunk = await stream.read()
        print(
            "[PRODUCER] chunk read"
        )

        if not chunk:
            print(
                "[PRODUCER] EOF reached")
            break

        await queue.put(chunk)
        print(
            f"[PRODUCER] "
            f"queue={queue.qsize()}"
        )
    #
    # eof
    #

    await queue.put(None)