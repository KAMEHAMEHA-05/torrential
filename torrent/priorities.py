HIGH_PRIORITY = 7

NORMAL_PRIORITY = 1

NO_PRIORITY = 0


def update_priorities(

    handle,

    old_window,

    new_window
):

    #
    # remove old priorities
    #

    for piece in old_window - new_window:

        handle.piece_priority(

            piece,

            NORMAL_PRIORITY
        )

    #
    # add new priorities
    #

    for piece in new_window - old_window:

        handle.piece_priority(

            piece,

            HIGH_PRIORITY
        )


def apply_deadlines(

    handle,

    pieces,

    base_piece,

    startup=False
):

    #
    # VERY aggressive startup
    #

    if startup:

        multiplier = 0

    else:

        multiplier = 5

    for piece in pieces:

        handle.set_piece_deadline(

            piece,

            (piece - base_piece)
            *
            multiplier
        )