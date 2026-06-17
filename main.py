from production_line import ProductionLine
from cmms import CMMS


line = ProductionLine()
cmms = CMMS()

line.start()

for _ in range(20):

    bottle = line.process_bottle()

    if bottle and bottle.defective:

        if line.defective_bottles >= 10:

            cmms.create_work_order(
                "High number of defective bottles"
            )

            break

line.stop()

print("\n===== PRODUCTION REPORT =====")

print(
    f"Produced: {line.total_bottles}"
)

print(
    f"Good: {line.good_bottles}"
)

print(
    f"Defective: {line.defective_bottles}"
)
quality_rate = (
    line.good_bottles / line.total_bottles
) * 100

print(
    f"Quality Rate: {quality_rate:.2f}%"
)