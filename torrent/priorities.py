HIGH_PRIORITY = 7

NO_PRIORITY = 0


def set_stream_priorities(
    handle,
    current_piece,
    end_piece,
    buffer_window=32
):

    start = current_piece

    stop = min(
        current_piece + buffer_window,
        end_piece
    )

    for piece in range(start, stop):

        handle.piece_priority(
            piece,
            HIGH_PRIORITY
        )

        handle.set_piece_deadline(
            piece,
            (piece - start) * 50
        )