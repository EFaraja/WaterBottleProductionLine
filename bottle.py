class Bottle:
    def __init__(self, bottle_id):

        self.id = bottle_id

        self.has_bottle = False
        self.filled = False
        self.capped = False
        self.branded = False

        self.defective = False
        self.defect_reason = None

    def __str__(self):

        return (
            f"Bottle {self.id} | "
            f"Filled:{self.filled} | "
            f"Capped:{self.capped} | "
            f"Branded:{self.branded} | "
            f"Defective:{self.defective}"
        )