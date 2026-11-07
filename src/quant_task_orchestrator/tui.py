"""Read-only terminal overview sharing the API projection."""

import curses

from .store import Store


def render(workflows):
    lines = [
        "QUANT / TASK ORCHESTRATOR",
        "Execution and research evidence are separate. Promotion stays with the owner.",
        "",
    ]
    for workflow in workflows:
        lines.append(f"{workflow['status']:22} {workflow['title']}  [{workflow['workflow_id']}]")
        for step in workflow["steps"]:
            lines.append(
                f"  {step['id']:18} {step['kind']:9} {step['status']:14} {step['evidence_status']}"
            )
        lines.append("")
    return "\n".join(lines) if workflows else "\n".join(lines + ["No workflows."])


def run(database, *, once=False):
    def snapshot():
        with Store(database, readonly=True) as store:
            return render(store.list())

    if once:
        print(snapshot())
        return

    def display(screen):
        screen.timeout(1000)
        offset = 0
        while True:
            lines = snapshot().splitlines()
            height, width = screen.getmaxyx()
            screen.erase()
            for row, line in enumerate(lines[offset : offset + max(0, height - 1)]):
                try:
                    screen.addnstr(row, 0, line, max(0, width - 1))
                except curses.error:
                    pass
            try:
                screen.addnstr(
                    height - 1,
                    0,
                    "q quit  |  arrows scroll  |  auto refresh 1s  |  read only",
                    max(0, width - 1),
                )
            except curses.error:
                pass
            screen.refresh()
            key = screen.getch()
            if key in (ord("q"), 27):
                break
            if key == curses.KEY_DOWN:
                offset = min(offset + 1, max(0, len(lines) - 1))
            elif key == curses.KEY_UP:
                offset = max(0, offset - 1)

    snapshot()  # Validate storage before entering terminal control mode.
    curses.wrapper(display)
