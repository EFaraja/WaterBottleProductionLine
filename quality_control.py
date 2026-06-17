import random


class QualityControl:

    @staticmethod
    def inspect(bottle):

        defects = []

        if not bottle.has_bottle:
            defects.append("Bottle Missing")

        if not bottle.filled:
            defects.append("Underfilled Bottle")

        if not bottle.capped:
            defects.append("Missing Cap")

        if not bottle.branded:
            defects.append("Missing Brand Label")

        if defects:
            bottle.defective = True
            bottle.defect_reason = ", ".join(defects)

        return bottle